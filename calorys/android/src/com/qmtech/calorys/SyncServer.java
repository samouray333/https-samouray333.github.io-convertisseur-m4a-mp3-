package com.qmtech.calorys;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Serveur HTTP minimal sur le Wi-Fi local, ouvert uniquement pendant que l'écran
 * « Synchroniser » est affiché (10 minutes maximum). Il ne fait que relayer des
 * données déjà chiffrées par l'appli : il ne les lit jamais.
 *   GET  /calorys/state  -> état chiffré proposé par ce téléphone
 *   POST /calorys/state  -> état fusionné chiffré envoyé par l'autre appareil
 */
public class SyncServer {
    public interface Bridge { void receive(String body); }

    private static final int MAX_BODY = 64 * 1024 * 1024;
    private static final long LIFETIME_MS = 10 * 60 * 1000;
    private final Bridge bridge;
    private ServerSocket server;
    private volatile String offer;
    private volatile String result;
    private CountDownLatch pending;
    private long startedAt;
    private int requests;

    public SyncServer(Bridge bridge) { this.bridge = bridge; }

    public synchronized int start(int port) throws Exception {
        stop();
        ServerSocket s = new ServerSocket();
        s.setReuseAddress(true);
        try { s.bind(new InetSocketAddress(port)); } catch (Exception e) { s.bind(new InetSocketAddress(0)); }
        server = s;
        offer = null;
        requests = 0;
        startedAt = System.currentTimeMillis();
        final ServerSocket ss = s;
        Thread t = new Thread(new Runnable() {
            @Override
            public void run() {
                while (!ss.isClosed()) {
                    try {
                        final Socket c = ss.accept();
                        if (System.currentTimeMillis() - startedAt > LIFETIME_MS) { c.close(); stop(); break; }
                        new Thread(new Runnable() { @Override public void run() { handle(c); } }).start();
                    } catch (Exception e) { break; }
                }
            }
        }, "calorys-sync");
        t.setDaemon(true);
        t.start();
        return s.getLocalPort();
    }

    public synchronized void stop() {
        if (server != null) { try { server.close(); } catch (Exception e) { /* ignore */ } server = null; }
        if (pending != null) pending.countDown();
    }

    public void setOffer(String o) { offer = o; }

    public void setResult(String r) {
        result = r;
        CountDownLatch l = pending;
        if (l != null) l.countDown();
    }

    public static List<String> addresses() {
        List<String> out = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && a.isSiteLocalAddress()) out.add(a.getHostAddress());
                }
            }
        } catch (Exception e) { /* aucune interface */ }
        return out;
    }

    private void handle(Socket c) {
        try {
            c.setSoTimeout(60000);
            InputStream in = new BufferedInputStream(c.getInputStream());
            String line = readLine(in);
            if (line == null) { c.close(); return; }
            String[] req = line.split(" ");
            String method = req[0], path = req.length > 1 ? req[1] : "/";
            int len = 0;
            String h;
            while ((h = readLine(in)) != null && !h.isEmpty()) {
                int i = h.indexOf(':');
                if (i > 0 && h.substring(0, i).trim().equalsIgnoreCase("Content-Length")) len = Integer.parseInt(h.substring(i + 1).trim());
            }
            OutputStream out = c.getOutputStream();
            synchronized (this) { requests++; }
            if (requests > 60) { reply(out, 429, "{\"error\":\"trop de requêtes\"}"); c.close(); return; }
            if (method.equals("OPTIONS")) { reply(out, 204, ""); c.close(); return; }
            if (path.startsWith("/calorys/hello")) { reply(out, 200, "{\"app\":\"Calorys\",\"ok\":true}"); c.close(); return; }
            if (!path.startsWith("/calorys/state")) { reply(out, 404, "{\"error\":\"introuvable\"}"); c.close(); return; }
            if (method.equals("GET")) {
                String o = offer;
                if (o == null) reply(out, 503, "{\"error\":\"pas prêt\"}"); else reply(out, 200, o);
                c.close();
                return;
            }
            if (method.equals("POST")) {
                if (len <= 0 || len > MAX_BODY) { reply(out, 413, "{\"error\":\"taille invalide\"}"); c.close(); return; }
                byte[] body = new byte[len];
                int off = 0, n;
                while (off < len && (n = in.read(body, off, len - off)) > 0) off += n;
                CountDownLatch latch = new CountDownLatch(1);
                synchronized (this) { pending = latch; result = null; }
                bridge.receive(new String(body, 0, off, StandardCharsets.UTF_8));
                latch.await(45, TimeUnit.SECONDS);
                String r = result;
                reply(out, 200, r != null ? r : "{\"ok\":false,\"error\":\"pas de réponse du téléphone\"}");
                c.close();
                return;
            }
            reply(out, 405, "{\"error\":\"méthode\"}");
            c.close();
        } catch (Exception e) {
            try { c.close(); } catch (Exception x) { /* ignore */ }
        }
    }

    private static String readLine(InputStream in) throws Exception {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) != -1) {
            if (ch == '\n') break;
            if (ch != '\r') b.write(ch);
            if (b.size() > 8192) throw new Exception("ligne trop longue");
        }
        if (ch == -1 && b.size() == 0) return null;
        return new String(b.toByteArray(), StandardCharsets.UTF_8);
    }

    private static void reply(OutputStream out, int code, String body) throws Exception {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        String status = code == 200 ? "OK" : code == 204 ? "No Content" : "Error";
        String head = "HTTP/1.1 " + code + " " + status + "\r\n"
                + "Content-Type: application/json; charset=utf-8\r\n"
                + "Content-Length: " + b.length + "\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                + "Access-Control-Allow-Headers: Content-Type\r\n"
                + "Access-Control-Allow-Private-Network: true\r\n"
                + "Cache-Control: no-store\r\n"
                + "Connection: close\r\n\r\n";
        out.write(head.getBytes(StandardCharsets.UTF_8));
        out.write(b);
        out.flush();
    }
}
