package android.graphics;

/** Version PC simplifiée de android.graphics.Path (garde seulement le rectangle englobant) pour les tests. */
public class Path {
    public enum FillType { WINDING, EVEN_ODD, INVERSE_WINDING, INVERSE_EVEN_ODD }
    public enum Op { DIFFERENCE, INTERSECT, UNION, XOR, REVERSE_DIFFERENCE }
    public enum Direction { CW, CCW }

    private float l = Float.MAX_VALUE, t = Float.MAX_VALUE, r = -Float.MAX_VALUE, b = -Float.MAX_VALUE;
    private FillType fill = FillType.WINDING;

    public Path() {}
    public Path(Path src) { if (src != null) set(src); }

    private void add(float x, float y) { l = Math.min(l, x); t = Math.min(t, y); r = Math.max(r, x); b = Math.max(b, y); }
    public void set(Path p) { l = p.l; t = p.t; r = p.r; b = p.b; fill = p.fill; }
    public void reset() { l = t = Float.MAX_VALUE; r = b = -Float.MAX_VALUE; }
    public void rewind() { reset(); }
    public boolean isEmpty() { return l > r; }
    public void moveTo(float x, float y) { add(x, y); }
    public void lineTo(float x, float y) { add(x, y); }
    public void rMoveTo(float x, float y) {}
    public void rLineTo(float x, float y) {}
    public void quadTo(float x1, float y1, float x2, float y2) { add(x1, y1); add(x2, y2); }
    public void cubicTo(float x1, float y1, float x2, float y2, float x3, float y3) { add(x1, y1); add(x2, y2); add(x3, y3); }
    public void close() {}
    public void addRect(float a, float c, float d, float e, Direction dir) { add(a, c); add(d, e); }
    public void addRect(RectF rc, Direction dir) { add(rc.left, rc.top); add(rc.right, rc.bottom); }
    public void addPath(Path p) { if (!p.isEmpty()) { add(p.l, p.t); add(p.r, p.b); } }
    public void addPath(Path p, Matrix m) { addPath(p); }
    public void computeBounds(RectF out, boolean exact) {
        if (isEmpty()) out.set(0, 0, 0, 0); else out.set(l, t, r, b);
    }
    public void transform(Matrix m) {}
    public void transform(Matrix m, Path dst) { if (dst != null) dst.set(this); }
    public void setFillType(FillType f) { fill = f; }
    public FillType getFillType() { return fill; }
    public boolean op(Path p, Op op) { return true; }
    public boolean op(Path a, Path b2, Op op) { set(a); return true; }
    public void offset(float dx, float dy) { if (!isEmpty()) { l += dx; r += dx; t += dy; b += dy; } }
}
