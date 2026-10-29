package android.graphics;

/** Version PC minimale de android.graphics.Matrix pour les tests. */
public class Matrix {
    private final float[] v = {1, 0, 0, 0, 1, 0, 0, 0, 1};
    public Matrix() {}
    public Matrix(Matrix m) { if (m != null) setValues(m.v); }
    public void setValues(float[] a) { System.arraycopy(a, 0, v, 0, 9); }
    public void getValues(float[] a) { System.arraycopy(v, 0, a, 0, 9); }
    public void reset() { setValues(new float[]{1, 0, 0, 0, 1, 0, 0, 0, 1}); }
    public void set(Matrix m) { setValues(m.v); }
    public boolean isIdentity() { return v[0] == 1 && v[1] == 0 && v[2] == 0 && v[3] == 0 && v[4] == 1 && v[5] == 0; }
    public void mapPoints(float[] p) {
        for (int i = 0; i + 1 < p.length; i += 2) {
            float x = p[i], y = p[i + 1];
            p[i] = v[0] * x + v[1] * y + v[2];
            p[i + 1] = v[3] * x + v[4] * y + v[5];
        }
    }
    public boolean mapRect(RectF r) { return true; }
    public boolean preConcat(Matrix m) { return true; }
    public boolean postConcat(Matrix m) { return true; }
    public void setScale(float a, float b) {}
    public void setTranslate(float a, float b) {}
    public boolean postTranslate(float a, float b) { return true; }
    public boolean postScale(float a, float b) { return true; }
    public boolean preTranslate(float a, float b) { return true; }
    public boolean preScale(float a, float b) { return true; }
}
