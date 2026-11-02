package ru.ctf.meowsim;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.view.View;

public class CatBoxView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private boolean superposition = true;
    private boolean observed = false;
    private boolean catDead = false;
    private int hunger = 55;
    private int mood = 55;
    private int energy = 60;
    private int health = 80;
    private int cleanliness = 65;
    private int stability = 35;

    public CatBoxView(Context context) {
        super(context);
        setMinimumHeight(dp(260));
    }

    public void setState(boolean superposition, boolean observed, boolean catDead, int hunger, int mood, int energy, int health, int cleanliness, int stability) {
        this.superposition = superposition;
        this.observed = observed;
        this.catDead = catDead;
        this.hunger = hunger;
        this.mood = mood;
        this.energy = energy;
        this.health = health;
        this.cleanliness = cleanliness;
        this.stability = stability;
        invalidate();
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int width = MeasureSpec.getSize(widthMeasureSpec);
        int height = resolveSize(dp(300), heightMeasureSpec);
        setMeasuredDimension(width, height);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        int w = getWidth();
        int h = getHeight();
        float cx = w / 2f;

        drawBackdrop(canvas, w, h);
        drawQuantumRings(canvas, cx, h);
        drawBox(canvas, cx, h);
        drawCat(canvas, cx, h);
        drawSituation(canvas, w, h);
    }

    private void drawBackdrop(Canvas canvas, int w, int h) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(255, 249, 238));
        canvas.drawRoundRect(new RectF(0, 0, w, h), dp(22), dp(22), paint);

        paint.setColor(Color.rgb(219, 241, 238));
        canvas.drawCircle(w * 0.18f, h * 0.18f, dp(46), paint);
        paint.setColor(Color.rgb(250, 220, 190));
        canvas.drawCircle(w * 0.82f, h * 0.22f, dp(54), paint);
    }

    private void drawQuantumRings(Canvas canvas, float cx, int h) {
        if (!superposition) {
            return;
        }
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(2));
        paint.setColor(Color.rgb(111, 156, 164));
        canvas.drawOval(new RectF(cx - dp(118), dp(30), cx + dp(118), dp(170)), paint);
        canvas.save();
        canvas.rotate(22, cx, dp(100));
        canvas.drawOval(new RectF(cx - dp(118), dp(30), cx + dp(118), dp(170)), paint);
        canvas.restore();

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(76, 129, 139));
        canvas.drawCircle(cx + dp(92), dp(98), dp(5), paint);
        canvas.drawCircle(cx - dp(88), dp(112), dp(4), paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(dp(12));
        paint.setColor(Color.rgb(64, 104, 112));
        canvas.drawText("стабильность " + stability, cx, dp(34), paint);
    }

    private void drawBox(Canvas canvas, float cx, int h) {
        float top = h - dp(112);
        float left = cx - dp(128);
        float right = cx + dp(128);
        float bottom = h - dp(20);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(195, 132, 76));
        canvas.drawRoundRect(new RectF(left, top, right, bottom), dp(14), dp(14), paint);

        paint.setColor(Color.rgb(225, 166, 103));
        path.reset();
        path.moveTo(left + dp(12), top);
        path.lineTo(cx, top - dp(42));
        path.lineTo(right - dp(12), top);
        path.close();
        canvas.drawPath(path, paint);

        paint.setColor(Color.rgb(149, 91, 52));
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(4));
        canvas.drawLine(cx, top - dp(38), cx, bottom - dp(8), paint);
        canvas.drawRoundRect(new RectF(left, top, right, bottom), dp(14), dp(14), paint);
    }

    private void drawCat(Canvas canvas, float cx, int h) {
        float headY = h - dp(144);
        float bodyY = h - dp(120);
        int fur = catDead ? Color.rgb(178, 184, 188) : Color.rgb(255, 190, 118);
        int furDark = catDead ? Color.rgb(126, 135, 141) : Color.rgb(201, 78, 55);
        int outline = Color.rgb(72, 55, 42);
        if (health < 35 && !catDead) {
            fur = Color.rgb(238, 199, 150);
            furDark = Color.rgb(173, 128, 95);
        }

        drawTail(canvas, cx - dp(76), bodyY + dp(28), fur, furDark, outline);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(fur);

        // This cat is intentionally round and sticker-like: one big head-body shape.
        path.reset();
        path.moveTo(cx - dp(62), headY - dp(22));
        path.lineTo(cx - dp(78), headY - dp(76));
        path.lineTo(cx - dp(28), headY - dp(48));
        path.close();
        canvas.drawPath(path, paint);

        path.reset();
        path.moveTo(cx + dp(62), headY - dp(22));
        path.lineTo(cx + dp(78), headY - dp(76));
        path.lineTo(cx + dp(28), headY - dp(48));
        path.close();
        canvas.drawPath(path, paint);

        canvas.drawRoundRect(new RectF(cx - dp(78), headY - dp(58), cx + dp(78), headY + dp(78)), dp(42), dp(42), paint);

        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(4));
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setColor(outline);
        canvas.drawRoundRect(new RectF(cx - dp(78), headY - dp(58), cx + dp(78), headY + dp(78)), dp(42), dp(42), paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(235, 65, 54));
        path.reset();
        path.moveTo(cx - dp(59), headY - dp(29));
        path.lineTo(cx - dp(67), headY - dp(58));
        path.lineTo(cx - dp(39), headY - dp(42));
        path.close();
        canvas.drawPath(path, paint);
        path.reset();
        path.moveTo(cx + dp(59), headY - dp(29));
        path.lineTo(cx + dp(67), headY - dp(58));
        path.lineTo(cx + dp(39), headY - dp(42));
        path.close();
        canvas.drawPath(path, paint);

        drawStripe(canvas, cx - dp(80), headY - dp(12), cx - dp(50), headY - dp(20), cx - dp(56), headY - dp(2), furDark);
        drawStripe(canvas, cx - dp(82), headY + dp(14), cx - dp(48), headY + dp(12), cx - dp(58), headY + dp(28), furDark);
        drawStripe(canvas, cx + dp(80), headY - dp(12), cx + dp(50), headY - dp(20), cx + dp(56), headY - dp(2), furDark);
        drawStripe(canvas, cx + dp(82), headY + dp(14), cx + dp(48), headY + dp(12), cx + dp(58), headY + dp(28), furDark);
        paint.setColor(furDark);
        canvas.drawRoundRect(new RectF(cx - dp(13), headY - dp(58), cx + dp(13), headY - dp(32)), dp(8), dp(8), paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(145, 84, 49));
        canvas.drawRoundRect(new RectF(cx - dp(38), bodyY + dp(50), cx - dp(12), bodyY + dp(74)), dp(10), dp(10), paint);
        canvas.drawRoundRect(new RectF(cx + dp(12), bodyY + dp(50), cx + dp(38), bodyY + dp(74)), dp(10), dp(10), paint);

        paint.setColor(outline);
        if (catDead || observed) {
            paint.setStrokeWidth(dp(4));
            canvas.drawLine(cx - dp(34), headY - dp(6), cx - dp(16), headY + dp(12), paint);
            canvas.drawLine(cx - dp(16), headY - dp(6), cx - dp(34), headY + dp(12), paint);
            canvas.drawLine(cx + dp(16), headY - dp(6), cx + dp(34), headY + dp(12), paint);
            canvas.drawLine(cx + dp(34), headY - dp(6), cx + dp(16), headY + dp(12), paint);
        } else if (energy < 30) {
            paint.setStrokeWidth(dp(4));
            canvas.drawArc(new RectF(cx - dp(54), headY - dp(10), cx - dp(16), headY + dp(18)), 15, 150, false, paint);
            canvas.drawArc(new RectF(cx + dp(16), headY - dp(10), cx + dp(54), headY + dp(18)), 15, 150, false, paint);
        } else if (hunger < 30) {
            drawBigEye(canvas, cx - dp(27), headY, dp(22), dp(31), true);
            drawBigEye(canvas, cx + dp(27), headY, dp(22), dp(31), true);
            paint.setStyle(Paint.Style.FILL);
        } else {
            drawBigEye(canvas, cx - dp(27), headY, dp(24), dp(32), false);
            drawBigEye(canvas, cx + dp(27), headY, dp(24), dp(32), false);
        }

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(111, 57, 42));
        path.reset();
        path.moveTo(cx, headY + dp(15));
        path.lineTo(cx - dp(8), headY + dp(27));
        path.lineTo(cx + dp(8), headY + dp(27));
        path.close();
        canvas.drawPath(path, paint);

        if (mood >= 70 && hunger >= 30 && health >= 35 && !catDead && !observed) {
            paint.setColor(Color.rgb(255, 104, 112));
            canvas.drawOval(new RectF(cx - dp(14), headY + dp(28), cx + dp(14), headY + dp(52)), paint);
            paint.setColor(Color.rgb(255, 174, 178));
            canvas.drawOval(new RectF(cx - dp(8), headY + dp(38), cx + dp(8), headY + dp(52)), paint);
        } else {
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(dp(4));
            paint.setColor(outline);
            canvas.drawArc(new RectF(cx - dp(17), headY + dp(31), cx + dp(17), headY + dp(52)), 205, 130, false, paint);
        }

        paint.setStrokeWidth(dp(2));
        paint.setColor(outline);
        canvas.drawLine(cx - dp(12), headY + dp(20), cx - dp(62), headY + dp(8), paint);
        canvas.drawLine(cx - dp(12), headY + dp(28), cx - dp(64), headY + dp(30), paint);
        canvas.drawLine(cx + dp(12), headY + dp(20), cx + dp(62), headY + dp(8), paint);
        canvas.drawLine(cx + dp(12), headY + dp(28), cx + dp(64), headY + dp(30), paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(250, 230, 138));
        canvas.drawCircle(cx + dp(56), bodyY - dp(14), dp(10), paint);

        if (health < 35 && !catDead) {
            paint.setColor(Color.rgb(245, 245, 245));
            canvas.drawRoundRect(new RectF(cx - dp(48), headY - dp(34), cx - dp(12), headY - dp(18)), dp(7), dp(7), paint);
            paint.setColor(Color.rgb(208, 82, 91));
            canvas.drawRect(cx - dp(33), headY - dp(32), cx - dp(25), headY - dp(20), paint);
            canvas.drawRect(cx - dp(38), headY - dp(28), cx - dp(20), headY - dp(24), paint);
        }

        if (cleanliness < 35) {
            paint.setColor(Color.rgb(106, 85, 65));
            canvas.drawCircle(cx - dp(50), bodyY - dp(14), dp(6), paint);
            canvas.drawCircle(cx + dp(46), bodyY + dp(16), dp(5), paint);
            canvas.drawCircle(cx + dp(4), bodyY + dp(42), dp(4), paint);
        }

        if (mood > 80 && health >= 35 && hunger >= 30 && !observed && !catDead) {
            paint.setColor(Color.rgb(236, 102, 116));
            drawHeart(canvas, cx - dp(86), headY - dp(52), dp(8));
            drawHeart(canvas, cx + dp(86), headY - dp(42), dp(7));
        }
    }

    private void drawTail(Canvas canvas, float x, float y, int fur, int furDark, int outline) {
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeWidth(dp(34));
        paint.setColor(fur);
        path.reset();
        path.moveTo(x, y);
        path.cubicTo(x - dp(84), y - dp(4), x - dp(112), y + dp(26), x - dp(154), y + dp(8));
        canvas.drawPath(path, paint);

        paint.setStrokeWidth(dp(38));
        paint.setColor(outline);
        canvas.drawPath(path, paint);
        paint.setStrokeWidth(dp(30));
        paint.setColor(fur);
        canvas.drawPath(path, paint);

        paint.setStrokeWidth(dp(5));
        paint.setColor(furDark);
        for (int i = 0; i < 4; i++) {
            float sx = x - dp(34 + i * 26);
            canvas.drawLine(sx, y - dp(15), sx + dp(8), y + dp(12), paint);
        }
        paint.setStrokeCap(Paint.Cap.BUTT);
    }

    private void drawBigEye(Canvas canvas, float x, float y, float rx, float ry, boolean hungry) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.WHITE);
        canvas.drawOval(new RectF(x - rx, y - ry, x + rx, y + ry), paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(3));
        paint.setColor(Color.rgb(72, 55, 42));
        canvas.drawOval(new RectF(x - rx, y - ry, x + rx, y + ry), paint);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(31, 35, 37));
        float pupilOffset = hungry ? dp(2) : 0;
        canvas.drawCircle(x + pupilOffset, y + dp(2), hungry ? dp(7) : dp(8), paint);
        paint.setColor(Color.WHITE);
        canvas.drawCircle(x + pupilOffset + dp(3), y - dp(2), dp(3), paint);
    }

    private void drawStripe(Canvas canvas, float x1, float y1, float x2, float y2, float x3, float y3, int color) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(color);
        path.reset();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        path.lineTo(x3, y3);
        path.close();
        canvas.drawPath(path, paint);
    }

    private void drawSituation(Canvas canvas, int w, int h) {
        if (hunger < 30 && !catDead) {
            drawBowl(canvas, w * 0.22f, h - dp(48));
        }
        if (energy < 30 && !catDead) {
            drawSleepMarks(canvas, w * 0.73f, dp(64));
        }
        if (cleanliness < 35) {
            drawSmellLines(canvas, w * 0.78f, h - dp(84));
        }
        if (stability < 70 && superposition) {
            drawWarning(canvas, w * 0.18f, dp(72));
        }
    }

    private void drawBowl(Canvas canvas, float x, float y) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(104, 164, 177));
        canvas.drawOval(new RectF(x - dp(34), y - dp(12), x + dp(34), y + dp(16)), paint);
        paint.setColor(Color.rgb(250, 230, 138));
        canvas.drawOval(new RectF(x - dp(22), y - dp(17), x + dp(22), y - dp(2)), paint);
    }

    private void drawSleepMarks(Canvas canvas, float x, float y) {
        paint.setStyle(Paint.Style.FILL);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        paint.setColor(Color.rgb(76, 129, 139));
        paint.setTextSize(dp(18));
        canvas.drawText("Z", x, y, paint);
        paint.setTextSize(dp(14));
        canvas.drawText("Z", x + dp(22), y - dp(18), paint);
        paint.setTextSize(dp(11));
        canvas.drawText("Z", x + dp(40), y - dp(34), paint);
        paint.setTypeface(android.graphics.Typeface.DEFAULT);
    }

    private void drawSmellLines(Canvas canvas, float x, float y) {
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(3));
        paint.setColor(Color.rgb(106, 85, 65));
        for (int i = 0; i < 3; i++) {
            float dx = i * dp(12);
            path.reset();
            path.moveTo(x + dx, y);
            path.cubicTo(x + dx - dp(8), y - dp(14), x + dx + dp(10), y - dp(24), x + dx, y - dp(38));
            canvas.drawPath(path, paint);
        }
    }

    private void drawWarning(Canvas canvas, float x, float y) {
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.rgb(245, 194, 94));
        path.reset();
        path.moveTo(x, y - dp(28));
        path.lineTo(x - dp(26), y + dp(20));
        path.lineTo(x + dp(26), y + dp(20));
        path.close();
        canvas.drawPath(path, paint);
        paint.setColor(Color.rgb(74, 57, 43));
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(dp(24));
        canvas.drawText("!", x, y + dp(12), paint);
    }

    private void drawHeart(Canvas canvas, float x, float y, float size) {
        path.reset();
        path.moveTo(x, y + size);
        path.cubicTo(x - size * 2, y - size * 0.3f, x - size, y - size * 1.5f, x, y - size * 0.5f);
        path.cubicTo(x + size, y - size * 1.5f, x + size * 2, y - size * 0.3f, x, y + size);
        canvas.drawPath(path, paint);
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}
