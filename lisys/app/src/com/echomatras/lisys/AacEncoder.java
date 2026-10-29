package com.echomatras.lisys;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;

import java.io.File;
import java.nio.ByteBuffer;

/** Encode du son PCM 16 bits mono en AAC dans un fichier .m4a (encodeur matériel d'Android). */
final class AacEncoder {
    private final MediaCodec codec;
    private final MediaMuxer muxer;
    private final MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
    private final int rate;
    private int track = -1;
    private boolean muxing;
    private long samples;

    AacEncoder(File out, int sampleRate) throws Exception {
        rate = sampleRate;
        MediaFormat f = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, sampleRate, 1);
        f.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC);
        f.setInteger(MediaFormat.KEY_BIT_RATE, 64000);
        f.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16384);
        codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC);
        codec.configure(f, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        codec.start();
        muxer = new MediaMuxer(out.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
    }

    int sampleRate() { return rate; }

    long durationMs() { return samples * 1000L / rate; }

    /** pcm : échantillons 16 bits little-endian mono. */
    void write(byte[] pcm, int off, int len) throws Exception {
        while (len > 0) {
            int idx = codec.dequeueInputBuffer(10000);
            if (idx >= 0) {
                ByteBuffer buf = codec.getInputBuffer(idx);
                buf.clear();
                int n = Math.min(buf.remaining(), len);
                n -= n % 2;
                if (n <= 0) n = Math.min(2, len);
                buf.put(pcm, off, n);
                long pts = samples * 1000000L / rate;
                codec.queueInputBuffer(idx, 0, n, pts, 0);
                samples += n / 2;
                off += n;
                len -= n;
            }
            drain(false);
        }
    }

    void silence(int ms) throws Exception {
        int n = rate * ms / 1000 * 2;
        byte[] z = new byte[Math.min(n, 32768)];
        while (n > 0) {
            int k = Math.min(n, z.length);
            write(z, 0, k);
            n -= k;
        }
    }

    private void drain(boolean eos) {
        while (true) {
            int idx = codec.dequeueOutputBuffer(info, eos ? 10000 : 0);
            if (idx == MediaCodec.INFO_TRY_AGAIN_LATER) {
                if (!eos) return;
                continue;
            }
            if (idx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                track = muxer.addTrack(codec.getOutputFormat());
                muxer.start();
                muxing = true;
                continue;
            }
            if (idx < 0) continue;
            ByteBuffer out = codec.getOutputBuffer(idx);
            if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) info.size = 0;
            if (info.size > 0 && muxing && out != null) {
                out.position(info.offset);
                out.limit(info.offset + info.size);
                muxer.writeSampleData(track, out, info);
            }
            codec.releaseOutputBuffer(idx, false);
            if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) return;
        }
    }

    void finish() throws Exception {
        int idx;
        do {
            idx = codec.dequeueInputBuffer(10000);
            if (idx < 0) drain(false);
        } while (idx < 0);
        codec.queueInputBuffer(idx, 0, 0, samples * 1000000L / rate, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
        drain(true);
        release();
    }

    void release() {
        try { codec.stop(); } catch (Exception ignored) {}
        try { codec.release(); } catch (Exception ignored) {}
        try { if (muxing) muxer.stop(); } catch (Exception ignored) {}
        try { muxer.release(); } catch (Exception ignored) {}
        muxing = false;
    }
}
