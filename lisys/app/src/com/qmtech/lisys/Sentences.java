package com.qmtech.lisys;

import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Découpage en phrases, pour lire et surligner phrase par phrase. */
public final class Sentences {
    private Sentences() {}

    /** Au-delà, on coupe une phrase trop longue sur une virgule ou un espace. */
    private static final int MAX_LEN = 320;

    /** Renvoie les phrases avec leurs positions [début, fin[ dans le paragraphe. */
    public static List<int[]> bounds(String p) {
        List<int[]> raw = new ArrayList<int[]>();
        BreakIterator it = BreakIterator.getSentenceInstance(Locale.FRENCH);
        it.setText(p);
        int start = it.first();
        for (int end = it.next(); end != BreakIterator.DONE; start = end, end = it.next()) {
            raw.add(new int[]{start, end});
        }
        if (raw.isEmpty()) raw.add(new int[]{0, p.length()});

        // Recolle les morceaux trop courts ("M." "Dr." "1." etc.) à la phrase suivante.
        List<int[]> merged = new ArrayList<int[]>();
        for (int[] b : raw) {
            String s = p.substring(b[0], b[1]).trim();
            if (!merged.isEmpty()) {
                int[] last = merged.get(merged.size() - 1);
                String prev = p.substring(last[0], last[1]).trim();
                if (prev.length() <= 4 || isAbbreviation(prev)) {
                    last[1] = b[1];
                    continue;
                }
            }
            if (s.length() == 0 && !merged.isEmpty()) {
                merged.get(merged.size() - 1)[1] = b[1];
                continue;
            }
            merged.add(new int[]{b[0], b[1]});
        }

        List<int[]> out = new ArrayList<int[]>();
        for (int[] b : merged) splitLong(p, b[0], b[1], out);
        return out;
    }

    public static List<String> split(String p) {
        List<String> out = new ArrayList<String>();
        for (int[] b : bounds(p)) out.add(p.substring(b[0], b[1]));
        return out;
    }

    private static boolean isAbbreviation(String s) {
        String[] abbr = {" M.", " Mme.", " Dr.", " St.", " p.", " cf.", " etc.", " av.", " n°."};
        String t = " " + s;
        for (String a : abbr) if (t.endsWith(a)) return true;
        return false;
    }

    private static void splitLong(String p, int start, int end, List<int[]> out) {
        while (end - start > MAX_LEN) {
            int cut = -1;
            // Cherche une ponctuation faible, de préférence vers la fin de la fenêtre.
            for (int i = start + MAX_LEN; i > start + MAX_LEN / 3; i--) {
                char c = p.charAt(i);
                if (c == ',' || c == ';' || c == ':' || c == ')' || c == '—') { cut = i + 1; break; }
            }
            if (cut < 0) {
                for (int i = start + MAX_LEN; i > start + MAX_LEN / 3; i--) {
                    if (p.charAt(i) == ' ') { cut = i + 1; break; }
                }
            }
            if (cut < 0) cut = start + MAX_LEN;
            out.add(new int[]{start, cut});
            start = cut;
        }
        if (end > start) out.add(new int[]{start, end});
    }
}
