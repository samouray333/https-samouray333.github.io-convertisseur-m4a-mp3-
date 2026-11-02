package com.qmtech.bimys;

import android.content.Intent;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BimysIntentPlugin.class);
        super.onCreate(savedInstanceState);
        BimysIntentPlugin.handleIntent(this, getIntent(), false);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        BimysIntentPlugin.handleIntent(this, intent, true);
    }
}
