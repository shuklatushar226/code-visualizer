package dsaviz;

import com.sun.jdi.*;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.event.*;
import com.sun.jdi.request.EventRequest;
import com.sun.jdi.request.EventRequestManager;
import com.sun.jdi.request.ExceptionRequest;
import com.sun.jdi.request.StepRequest;

import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;

/**
 * JDI-driven Java tracer for the DSA Code Visualizer.
 *
 * Runs as a *debugger* process: it launches the user's compiled class as a child VM,
 * single-steps it line-by-line (restricted to user code), decodes locals + the reachable
 * object graph via JDI's typed value API, and writes the complete Trace Event Protocol
 * JSON document to its own stdout. The debuggee's stdout/stderr are captured separately
 * via vm.process() and never mix with the JSON.
 *
 * Invoked by java_tracer/__init__.py:
 *   java -cp <helperDir>:<userDir> dsaviz.Tracer --main <Class> --cp <userDir>
 *        --max-events <N> --source-file <Name.java>
 * The debuggee's stdin is relayed from this process's own stdin.
 */
public final class Tracer {

    private static final String[] EXCLUDE_PREFIXES =
        {"java.", "javax.", "sun.", "jdk.", "com.sun.", "kotlin."};
    private static final String[] EXCLUDE_FILTERS =
        {"java.*", "javax.*", "sun.*", "jdk.*", "com.sun.*", "kotlin.*"};

    private static final int MAX_DEPTH = 8;
    private static final int MAX_OBJECTS = 2000;
    private static final int MAX_ITEMS = 1000;
    private static final int MAX_STR = 1024;
    private static final long MAX_SAFE_INT = 9007199254740991L; // 2^53 - 1

    private final String mainClass;
    private final String classpath;
    private final int maxEvents;
    private final String sourceFile;

    Tracer(String mainClass, String classpath, int maxEvents, String sourceFile) {
        this.mainClass = mainClass;
        this.classpath = classpath;
        this.maxEvents = maxEvents;
        this.sourceFile = (sourceFile == null || sourceFile.isEmpty()) ? mainClass + ".java" : sourceFile;
    }

    public static void main(String[] argv) throws Exception {
        Map<String, String> a = parseArgs(argv);
        Tracer tracer = new Tracer(
            a.getOrDefault("--main", "Main"),
            a.getOrDefault("--cp", "."),
            Integer.parseInt(a.getOrDefault("--max-events", "5000")),
            a.getOrDefault("--source-file", ""));
        Map<String, Object> doc = tracer.run();
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
        out.print(Json.write(doc));
        out.flush();
    }

    private static Map<String, String> parseArgs(String[] argv) {
        Map<String, String> m = new LinkedHashMap<>();
        for (int i = 0; i + 1 < argv.length; i += 2) m.put(argv[i], argv[i + 1]);
        return m;
    }

    // ------------------------------------------------------------------ //
    // driver
    // ------------------------------------------------------------------ //

    Map<String, Object> run() {
        List<Object> events = new ArrayList<>();
        String exitStatus = "ok";
        String exitMessage = null;
        boolean truncated = false;
        String stdoutText = "";
        String stderrText = "";

        VirtualMachine vm = null;
        try {
            vm = launch();
            Process proc = vm.process();
            StreamPump outPump = new StreamPump(proc.getInputStream());
            StreamPump errPump = new StreamPump(proc.getErrorStream());
            outPump.start();
            errPump.start();
            Thread inRelay = new Thread(() -> relay(System.in, proc.getOutputStream()));
            inRelay.setDaemon(true);
            inRelay.start();

            EventRequestManager erm = vm.eventRequestManager();
            EventQueue queue = vm.eventQueue();
            ThreadReference mainThread = null;
            int prevDepth = 0;
            int stdoutMark = 0;

            outer:
            while (true) {
                EventSet set;
                try {
                    set = queue.remove();
                } catch (Exception e) {
                    break;
                }
                boolean resume = true;
                for (Event ev : set) {
                    if (ev instanceof VMStartEvent) {
                        mainThread = ((VMStartEvent) ev).thread();
                        installRequests(erm, mainThread);
                    } else if (ev instanceof StepEvent) {
                        StepEvent se = (StepEvent) ev;
                        if (se.thread() != mainThread) continue;
                        if (!isUserLocation(se.location())) continue;
                        if (events.size() >= maxEvents) {
                            truncated = true;
                            resume = false;
                            break outer;
                        }

                        Snapshot snap = snapshotStack(se.thread());
                        int depth = snap.frames.size();
                        Decoded dec = decodeStack(snap, se.thread());

                        if (depth > prevDepth) {
                            events.add(makeEvent(events.size(), "call", dec, null, null));
                        } else if (depth < prevDepth) {
                            events.add(makeEvent(events.size(), "return", dec, null, null));
                        }
                        prevDepth = depth;
                        if (events.size() >= maxEvents) {
                            truncated = true;
                            resume = false;
                            break outer;
                        }
                        String all = outPump.snapshot();
                        String delta = all.length() > stdoutMark ? all.substring(stdoutMark) : null;
                        stdoutMark = all.length();
                        events.add(makeEvent(events.size(), "step", dec, delta, null));
                    } else if (ev instanceof ExceptionEvent) {
                        ExceptionEvent xe = (ExceptionEvent) ev;
                        if (xe.thread() != mainThread) continue;
                        Map<String, Object> exc = exceptionInfo(xe);
                        if (events.size() < maxEvents) {
                            Snapshot snap = snapshotStack(xe.thread());
                            Decoded dec = decodeStack(snap, xe.thread());
                            events.add(makeEvent(events.size(), "exception", dec, null, exc));
                        }
                        exitStatus = "error";
                        exitMessage = exc.get("type") + ": " + exc.get("message");
                    } else if (ev instanceof VMDeathEvent || ev instanceof VMDisconnectEvent) {
                        resume = false;
                        break outer;
                    }
                }
                if (resume) {
                    set.resume();
                } else {
                    break;
                }
            }

            try {
                outPump.join(800);
                errPump.join(300);
            } catch (InterruptedException ignore) {
            }
            stdoutText = outPump.snapshot();
            stderrText = errPump.snapshot();
            try {
                vm.exit(0);
            } catch (Exception ignore) {
            }
        } catch (Throwable t) {
            exitStatus = "error";
            exitMessage = t.toString();
            if (vm != null) {
                try {
                    vm.exit(1);
                } catch (Exception ignore) {
                }
            }
        }

        Map<String, Object> exit = new LinkedHashMap<>();
        exit.put("status", exitStatus);
        exit.put("message", exitMessage);
        exit.put("truncated", truncated);

        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("version", "0.1");
        doc.put("language", "java");
        doc.put("source", "");   // filled by the Python wrapper
        doc.put("stdin", "");    // filled by the Python wrapper
        doc.put("stdout", stdoutText);
        doc.put("stderr", stderrText);
        doc.put("exit", exit);
        doc.put("events", events);
        return doc;
    }

    private VirtualMachine launch() throws Exception {
        LaunchingConnector conn = Bootstrap.virtualMachineManager().defaultConnector();
        Map<String, Connector.Argument> args = conn.defaultArguments();
        args.get("main").setValue(mainClass);
        args.get("options").setValue("-cp " + classpath);
        args.get("suspend").setValue("true");
        return conn.launch(args);
    }

    private void installRequests(EventRequestManager erm, ThreadReference mainThread) {
        StepRequest step = erm.createStepRequest(mainThread, StepRequest.STEP_LINE, StepRequest.STEP_INTO);
        for (String f : EXCLUDE_FILTERS) step.addClassExclusionFilter(f);
        step.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
        step.enable();

        ExceptionRequest exc = erm.createExceptionRequest(null, false, true);
        for (String f : EXCLUDE_FILTERS) exc.addClassExclusionFilter(f);
        exc.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
        exc.enable();
    }

    private boolean isUserLocation(Location loc) {
        try {
            String cn = loc.declaringType().name();
            for (String p : EXCLUDE_PREFIXES) if (cn.startsWith(p)) return false;
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    // ------------------------------------------------------------------ //
    // frame snapshot (RAW values only — must precede any invokeMethod)
    // ------------------------------------------------------------------ //

    private static final class RawFrame {
        String func, file;
        int line;
        LinkedHashMap<String, Value> locals = new LinkedHashMap<>();
        List<String> args = new ArrayList<>();
    }

    private static final class Snapshot {
        List<RawFrame> frames = new ArrayList<>(); // top-first
    }

    private Snapshot snapshotStack(ThreadReference thread) {
        Snapshot snap = new Snapshot();
        List<StackFrame> frames;
        try {
            frames = thread.frames();
        } catch (Exception e) {
            return snap;
        }
        for (StackFrame f : frames) {
            Location loc;
            try {
                loc = f.location();
            } catch (Exception e) {
                continue;
            }
            if (!isUserLocation(loc)) continue;
            RawFrame rf = new RawFrame();
            Method m = loc.method();
            rf.func = m.name();
            try {
                rf.file = loc.sourceName();
            } catch (AbsentInformationException e) {
                rf.file = sourceFile;
            }
            rf.line = Math.max(0, loc.lineNumber());
            try {
                for (LocalVariable lv : m.arguments()) rf.args.add(lv.name());
            } catch (AbsentInformationException e) {
                // no debug info for args
            }
            try {
                ObjectReference self = f.thisObject();
                if (self != null) rf.locals.put("this", self);
            } catch (Exception e) {
                // static method or unavailable
            }
            try {
                List<LocalVariable> vis = f.visibleVariables();
                Map<LocalVariable, Value> vals = f.getValues(vis);
                for (LocalVariable lv : vis) rf.locals.put(lv.name(), vals.get(lv));
            } catch (AbsentInformationException e) {
                // compiled without -g, or synthetic frame
            } catch (Exception e) {
                // ignore frame-local read errors
            }
            snap.frames.add(rf);
        }
        return snap;
    }

    // ------------------------------------------------------------------ //
    // decode a whole stack (may invokeMethod for collections)
    // ------------------------------------------------------------------ //

    private static final class Decoded {
        List<Object> stack = new ArrayList<>();   // bottom-first
        Map<String, Object> heap = new LinkedHashMap<>();
        int line;
        String file;
    }

    private Decoded decodeStack(Snapshot snap, ThreadReference thread) {
        Decoded d = new Decoded();
        HeapState hs = new HeapState();
        // protocol wants bottom-of-stack first; snapshot is top-first
        for (int i = snap.frames.size() - 1; i >= 0; i--) {
            RawFrame rf = snap.frames.get(i);
            Map<String, Object> locals = new LinkedHashMap<>();
            for (Map.Entry<String, Value> e : rf.locals.entrySet()) {
                locals.put(e.getKey(), decodeValue(e.getValue(), thread, hs, 0));
            }
            Map<String, Object> frame = new LinkedHashMap<>();
            frame.put("func", rf.func);
            frame.put("file", rf.file);
            frame.put("line", rf.line);
            frame.put("locals", locals);
            frame.put("args", rf.args);
            d.stack.add(frame);
        }
        d.heap = hs.heap;
        if (!snap.frames.isEmpty()) {
            d.line = snap.frames.get(0).line;
            d.file = snap.frames.get(0).file;
        } else {
            d.line = 0;
            d.file = sourceFile;
        }
        return d;
    }

    private Map<String, Object> makeEvent(int t, String kind, Decoded dec, String stdoutDelta, Map<String, Object> exception) {
        Map<String, Object> ev = new LinkedHashMap<>();
        ev.put("t", t);
        ev.put("kind", kind);
        ev.put("line", dec.line);
        ev.put("file", dec.file);
        ev.put("stack", dec.stack);
        ev.put("heap", dec.heap);
        ev.put("stdout_delta", stdoutDelta);
        ev.put("exception", exception);
        return ev;
    }

    // ------------------------------------------------------------------ //
    // value / heap decoding
    // ------------------------------------------------------------------ //

    private static final class HeapState {
        Map<String, Object> heap = new LinkedHashMap<>();
        Set<Long> inProgress = new HashSet<>();
    }

    private Object decodeValue(Value v, ThreadReference t, HeapState hs, int depth) {
        if (v == null) return kv("kind", "none");
        if (v instanceof BooleanValue) return kv("kind", "bool", "v", ((BooleanValue) v).value());
        if (v instanceof CharValue) return kv("kind", "str", "v", String.valueOf(((CharValue) v).value()));
        if (v instanceof ByteValue) return intVal(((ByteValue) v).value());
        if (v instanceof ShortValue) return intVal(((ShortValue) v).value());
        if (v instanceof IntegerValue) return intVal(((IntegerValue) v).value());
        if (v instanceof LongValue) return longVal(((LongValue) v).value());
        if (v instanceof FloatValue) return floatVal(((FloatValue) v).value());
        if (v instanceof DoubleValue) return floatVal(((DoubleValue) v).value());
        if (v instanceof StringReference) return kv("kind", "str", "v", truncate(((StringReference) v).value()));
        if (v instanceof ObjectReference) return decodeObjectRef((ObjectReference) v, t, hs, depth);
        return kv("kind", "str", "v", v.toString());
    }

    private Object intVal(long n) {
        return kv("kind", "int", "v", n);
    }

    private Object longVal(long n) {
        if (n > MAX_SAFE_INT || n < -MAX_SAFE_INT) {
            return kv("kind", "int", "v", Long.toString(n), "big", Boolean.TRUE);
        }
        return kv("kind", "int", "v", n);
    }

    private Object floatVal(double d) {
        if (Double.isNaN(d)) return kv("kind", "float", "v", null, "special", "nan");
        if (Double.isInfinite(d)) return kv("kind", "float", "v", null, "special", d > 0 ? "inf" : "-inf");
        return kv("kind", "float", "v", d);
    }

    private Object decodeObjectRef(ObjectReference o, ThreadReference t, HeapState hs, int depth) {
        // Unwrap boxed primitives (Integer/Long/.../Character) to their scalar value so
        // List<Integer>/Map values render as 10, 20, 30 — not as object references.
        Object boxed = unwrapBoxed(o, t, hs, depth);
        if (boxed != null) return boxed;

        long uid = o.uniqueID();
        String id = "h_" + uid;
        if (hs.heap.containsKey(id)) return ref(id);
        String typeName = simpleName(safeTypeName(o));
        if (hs.inProgress.contains(uid)) {
            hs.heap.putIfAbsent(id, objStub(typeName));
            return ref(id);
        }
        if (depth >= MAX_DEPTH || hs.heap.size() >= MAX_OBJECTS) {
            hs.heap.put(id, objStub(typeName));
            return ref(id);
        }
        hs.inProgress.add(uid);
        try {
            Object decoded;
            ReferenceType rt = o.referenceType();
            if (o instanceof ArrayReference) {
                decoded = decodeArray((ArrayReference) o, t, hs, depth);
            } else if (rt instanceof ClassType && implementsIface((ClassType) rt, "java.util.Map")) {
                decoded = decodeMap(o, t, hs, depth);
            } else if (rt instanceof ClassType && implementsIface((ClassType) rt, "java.util.Set")) {
                decoded = decodeCollection(o, t, hs, depth, "set");
            } else if (rt instanceof ClassType && implementsIface((ClassType) rt, "java.util.Collection")) {
                decoded = decodeCollection(o, t, hs, depth, "list");
            } else {
                decoded = decodeFields(o, t, hs, depth);
            }
            hs.heap.put(id, decoded);
        } finally {
            hs.inProgress.remove(uid);
        }
        return ref(id);
    }

    private Object unwrapBoxed(ObjectReference o, ThreadReference t, HeapState hs, int depth) {
        String tn = safeTypeName(o);
        switch (tn) {
            case "java.lang.Integer":
            case "java.lang.Long":
            case "java.lang.Short":
            case "java.lang.Byte":
            case "java.lang.Character":
            case "java.lang.Boolean":
            case "java.lang.Float":
            case "java.lang.Double":
                try {
                    Field f = o.referenceType().fieldByName("value");
                    if (f != null) return decodeValue(o.getValue(f), t, hs, depth);
                } catch (Exception e) {
                    // fall through to ref decoding
                }
                return null;
            default:
                return null;
        }
    }

    private Object decodeArray(ArrayReference arr, ThreadReference t, HeapState hs, int depth) {
        List<Object> items = new ArrayList<>();
        int len = arr.length();
        int cap = Math.min(len, MAX_ITEMS);
        List<Value> vals = cap > 0 ? arr.getValues(0, cap) : Collections.emptyList();
        for (Value e : vals) items.add(decodeValue(e, t, hs, depth + 1));
        return kv("kind", "list", "items", items);
    }

    private Object decodeFields(ObjectReference o, ThreadReference t, HeapState hs, int depth) {
        ReferenceType rt = o.referenceType();
        LinkedHashMap<String, Object> fields = new LinkedHashMap<>();
        List<Field> all;
        try {
            all = rt.allFields();
        } catch (Exception e) {
            all = Collections.emptyList();
        }
        List<Field> nonStatic = new ArrayList<>();
        for (Field f : all) {
            if (!f.isStatic() && !f.isSynthetic()) nonStatic.add(f);
        }
        Map<Field, Value> vals;
        try {
            vals = o.getValues(nonStatic);
        } catch (Exception e) {
            vals = Collections.emptyMap();
        }
        for (Field f : nonStatic) {
            fields.put(f.name(), decodeValue(vals.get(f), t, hs, depth + 1));
        }
        return obj(simpleName(rt.name()), fields);
    }

    private Object decodeCollection(ObjectReference o, ThreadReference t, HeapState hs, int depth, String kind) {
        try {
            ArrayReference arr = (ArrayReference) invoke(o, t, "toArray", "()[Ljava/lang/Object;");
            List<Object> items = new ArrayList<>();
            int cap = Math.min(arr.length(), MAX_ITEMS);
            List<Value> vals = cap > 0 ? arr.getValues(0, cap) : Collections.emptyList();
            for (Value e : vals) items.add(decodeValue(e, t, hs, depth + 1));
            return kv("kind", kind, "items", items);
        } catch (Throwable ex) {
            return decodeFields(o, t, hs, depth);
        }
    }

    private Object decodeMap(ObjectReference o, ThreadReference t, HeapState hs, int depth) {
        try {
            ObjectReference entrySet = (ObjectReference) invoke(o, t, "entrySet", "()Ljava/util/Set;");
            ArrayReference arr = (ArrayReference) invoke(entrySet, t, "toArray", "()[Ljava/lang/Object;");
            List<Object> entries = new ArrayList<>();
            int cap = Math.min(arr.length(), MAX_ITEMS);
            List<Value> vals = cap > 0 ? arr.getValues(0, cap) : Collections.emptyList();
            for (Value ev : vals) {
                ObjectReference entry = (ObjectReference) ev;
                Value k = invoke(entry, t, "getKey", "()Ljava/lang/Object;");
                Value val = invoke(entry, t, "getValue", "()Ljava/lang/Object;");
                List<Object> pair = new ArrayList<>();
                pair.add(decodeValue(k, t, hs, depth + 1));
                pair.add(decodeValue(val, t, hs, depth + 1));
                entries.add(pair);
            }
            return kv("kind", "dict", "entries", entries);
        } catch (Throwable ex) {
            return decodeFields(o, t, hs, depth);
        }
    }

    private Value invoke(ObjectReference o, ThreadReference t, String name, String sig) throws Exception {
        ReferenceType rt = o.referenceType();
        List<Method> ms = rt.methodsByName(name, sig);
        if (ms.isEmpty()) ms = rt.methodsByName(name);
        if (ms.isEmpty()) throw new NoSuchMethodException(name);
        return o.invokeMethod(t, ms.get(0), Collections.emptyList(), ObjectReference.INVOKE_SINGLE_THREADED);
    }

    private boolean implementsIface(ClassType ct, String fqn) {
        try {
            for (InterfaceType it : ct.allInterfaces()) {
                if (it.name().equals(fqn)) return true;
            }
        } catch (Exception e) {
            // ignore
        }
        return false;
    }

    private Map<String, Object> exceptionInfo(ExceptionEvent xe) {
        String type = "Exception";
        String message = "";
        try {
            ObjectReference exc = xe.exception();
            type = simpleName(exc.referenceType().name());
            Field f = exc.referenceType().fieldByName("detailMessage");
            if (f != null) {
                Value mv = exc.getValue(f);
                if (mv instanceof StringReference) message = ((StringReference) mv).value();
            }
        } catch (Exception e) {
            // best effort
        }
        return kv("type", type, "message", message == null ? "" : message);
    }

    // ------------------------------------------------------------------ //
    // small helpers
    // ------------------------------------------------------------------ //

    private static String safeTypeName(ObjectReference o) {
        try {
            return o.referenceType().name();
        } catch (Exception e) {
            return "object";
        }
    }

    private static String simpleName(String fqn) {
        String s = fqn;
        int dot = s.lastIndexOf('.');
        if (dot >= 0) s = s.substring(dot + 1);
        int dollar = s.lastIndexOf('$');
        if (dollar >= 0 && dollar + 1 < s.length()) s = s.substring(dollar + 1);
        return s;
    }

    private static String truncate(String s) {
        if (s == null) return "";
        if (s.length() <= MAX_STR) return s;
        return s.substring(0, MAX_STR - 3) + "...";
    }

    private static Object ref(String id) {
        return kv("kind", "ref", "id", id);
    }

    private static Map<String, Object> objStub(String type) {
        return obj(type, new LinkedHashMap<>());
    }

    private static Map<String, Object> obj(String type, Map<String, Object> fields) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("kind", "object");
        m.put("type", type);
        m.put("fields", fields);
        return m;
    }

    /** Build an ordered map from alternating key/value pairs. */
    private static Map<String, Object> kv(Object... kvs) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kvs.length; i += 2) m.put((String) kvs[i], kvs[i + 1]);
        return m;
    }

    private static void relay(InputStream from, OutputStream to) {
        try {
            from.transferTo(to);
            to.flush();
        } catch (IOException ignore) {
        } finally {
            try {
                to.close();
            } catch (Exception ignore) {
            }
        }
    }

    /** Drains a child stream on a daemon thread so its pipe never blocks the debuggee. */
    private static final class StreamPump extends Thread {
        private final InputStream in;
        private final StringBuilder sb = new StringBuilder();

        StreamPump(InputStream in) {
            this.in = in;
            setDaemon(true);
        }

        @Override
        public void run() {
            try (Reader r = new InputStreamReader(in, StandardCharsets.UTF_8)) {
                char[] buf = new char[4096];
                int n;
                while ((n = r.read(buf)) != -1) {
                    synchronized (sb) {
                        sb.append(buf, 0, n);
                    }
                }
            } catch (IOException ignore) {
            }
        }

        String snapshot() {
            synchronized (sb) {
                return sb.toString();
            }
        }
    }

    // ------------------------------------------------------------------ //
    // minimal JSON writer (no external deps)
    // ------------------------------------------------------------------ //

    static final class Json {
        static String write(Object o) {
            StringBuilder sb = new StringBuilder();
            writeVal(sb, o);
            return sb.toString();
        }

        private static void writeVal(StringBuilder sb, Object o) {
            if (o == null) {
                sb.append("null");
            } else if (o instanceof String) {
                writeStr(sb, (String) o);
            } else if (o instanceof Boolean) {
                sb.append(o.toString());
            } else if (o instanceof Integer || o instanceof Long) {
                sb.append(o.toString());
            } else if (o instanceof Double || o instanceof Float) {
                double d = ((Number) o).doubleValue(); // finite by construction
                sb.append(Double.toString(d));
            } else if (o instanceof Map) {
                writeObj(sb, (Map<?, ?>) o);
            } else if (o instanceof List) {
                writeArr(sb, (List<?>) o);
            } else {
                writeStr(sb, o.toString());
            }
        }

        private static void writeObj(StringBuilder sb, Map<?, ?> m) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) sb.append(',');
                first = false;
                writeStr(sb, String.valueOf(e.getKey()));
                sb.append(':');
                writeVal(sb, e.getValue());
            }
            sb.append('}');
        }

        private static void writeArr(StringBuilder sb, List<?> list) {
            sb.append('[');
            boolean first = true;
            for (Object e : list) {
                if (!first) sb.append(',');
                first = false;
                writeVal(sb, e);
            }
            sb.append(']');
        }

        private static void writeStr(StringBuilder sb, String s) {
            sb.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"': sb.append("\\\""); break;
                    case '\\': sb.append("\\\\"); break;
                    case '\n': sb.append("\\n"); break;
                    case '\r': sb.append("\\r"); break;
                    case '\t': sb.append("\\t"); break;
                    case '\b': sb.append("\\b"); break;
                    case '\f': sb.append("\\f"); break;
                    default:
                        if (c < 0x20 || c == ' ' || c == ' ') {
                            sb.append(String.format("\\u%04x", (int) c));
                        } else {
                            sb.append(c);
                        }
                }
            }
            sb.append('"');
        }
    }
}
