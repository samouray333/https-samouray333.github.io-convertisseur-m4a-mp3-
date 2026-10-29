package android.util;

import org.xmlpull.v1.XmlPullParser;

/** Version PC de android.util.Xml pour les tests (même analyseur KXml qu'Android). */
public class Xml {
    public static XmlPullParser newPullParser() {
        return new com.android.org.kxml2.io.KXmlParser();
    }
}
