package com.sound.wear

import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.ColorBuilders.argb
import androidx.wear.protolayout.DimensionBuilders.dp
import androidx.wear.protolayout.DimensionBuilders.expand
import androidx.wear.protolayout.DimensionBuilders.sp
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.tiles.RequestBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import org.json.JSONObject

/** Kaydırınca açılan kart: çalan şarkı, önceki / çal-duraklat / sonraki. Dokununca uygulama açılır. */
class NowTile : TileService() {
    private val text = 0xFFFFFFFF.toInt()
    private val dim = 0xFFB8B8C0.toInt()

    override fun onTileRequest(req: RequestBuilders.TileRequest): ListenableFuture<TileBuilders.Tile> {
        val local = Where.watch(this)
        val device = Where.device(this)
        if (local) LocalPlayer.init(this)
        if (device != null) Remote.start(this)
        val click = req.currentState.lastClickableId
        when {
            local -> when (click) { "prev" -> LocalPlayer.previous(this); "toggle" -> LocalPlayer.toggle(this); "next" -> LocalPlayer.next(this) }
            device != null -> when (click) { "prev" -> Remote.cmd(device, "previous"); "toggle" -> Remote.cmd(device, "toggle"); "next" -> Remote.cmd(device, "next") }
            else -> when (click) { "prev" -> Link.command(this, "previous"); "toggle" -> Link.command(this, "toggle"); "next" -> Link.command(this, "next") }
        }
        val now = when {
            local -> LocalPlayer.state()
            device != null -> Remote.np(device)?.let { np ->
                val t = np.optJSONObject("track") ?: return@let null
                JSONObject().put("id", t.optString("id")).put("title", t.optString("title")).put("artist", t.optString("artist"))
                    .put("playing", np.optBoolean("playing"))
            }
            else -> Link.cached(this)
        }
        val accent = runCatching { android.graphics.Color.parseColor(now?.optString("accent") ?: "#8b5cf6") }.getOrDefault(0xFF8B5CF6.toInt())
        var playing = now?.optBoolean("playing") == true
        if (local) playing = LocalPlayer.playing
        else if (click == "toggle") playing = !playing  // telefondan yanıt gelmeden doğru görünsün
        val col = LayoutElementBuilders.Column.Builder().setWidth(expand()).setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
        col.addContent(txt(when { local -> "SOUND · SAAT"; device != null -> "SOUND · ${Remote.deviceName(device)}"; else -> "SOUND" }, 12f, accent, bold = true))
        col.addContent(space(6f))
        if (now == null || now.optString("id").isEmpty()) {
            col.addContent(txt("Şu an bir şey çalmıyor", 14f, text, bold = true))
            col.addContent(txt(if (local) "Dokun, kitaplıktan seç" else "Telefonda SOUND'u aç", 12f, dim))
        } else {
            col.addContent(txt(now.optString("title"), 15f, text, bold = true))
            col.addContent(txt(now.optString("artist"), 12f, dim))
        }
        col.addContent(space(12f))
        val row = LayoutElementBuilders.Row.Builder().setVerticalAlignment(LayoutElementBuilders.VERTICAL_ALIGN_CENTER)
        row.addContent(button("prev", "⏮", 44f, 0xFF2A2A30.toInt(), text))
        row.addContent(LayoutElementBuilders.Spacer.Builder().setWidth(dp(8f)).build())
        row.addContent(button("toggle", if (playing) "❚❚" else "▶", 56f, accent, if (lum(accent) > 0.55) 0xFF000000.toInt() else text))
        row.addContent(LayoutElementBuilders.Spacer.Builder().setWidth(dp(8f)).build())
        row.addContent(button("next", "⏭", 44f, 0xFF2A2A30.toInt(), text))
        col.addContent(row.build())

        val root = LayoutElementBuilders.Box.Builder().setWidth(expand()).setHeight(expand())
            .setModifiers(ModifiersBuilders.Modifiers.Builder()
                .setPadding(ModifiersBuilders.Padding.Builder().setStart(dp(20f)).setEnd(dp(20f)).build())
                .setClickable(ModifiersBuilders.Clickable.Builder().setId("open").setOnClick(
                    ActionBuilders.LaunchAction.Builder().setAndroidActivity(
                        ActionBuilders.AndroidActivity.Builder().setPackageName(packageName).setClassName("com.sound.wear.NowActivity").build(),
                    ).build(),
                ).build())
                .build())
            .addContent(col.build())
            .build()
        return Futures.immediateFuture(
            TileBuilders.Tile.Builder()
                .setResourcesVersion("1")
                .setFreshnessIntervalMillis(0)  // telefon yeni şarkı yazınca DataService günceller
                .setTileTimeline(TimelineBuilders.Timeline.fromLayoutElement(root))
                .build(),
        )
    }

    override fun onTileResourcesRequest(req: RequestBuilders.ResourcesRequest): ListenableFuture<ResourceBuilders.Resources> =
        Futures.immediateFuture(ResourceBuilders.Resources.Builder().setVersion("1").build())

    private fun lum(c: Int) = (0.2126 * android.graphics.Color.red(c) + 0.7152 * android.graphics.Color.green(c) + 0.0722 * android.graphics.Color.blue(c)) / 255

    private fun space(h: Float) = LayoutElementBuilders.Spacer.Builder().setHeight(dp(h)).build()

    private fun button(id: String, label: String, size: Float, bg: Int, fg: Int) =
        LayoutElementBuilders.Box.Builder().setWidth(dp(size)).setHeight(dp(size))
            .setModifiers(ModifiersBuilders.Modifiers.Builder()
                .setBackground(ModifiersBuilders.Background.Builder().setColor(argb(bg))
                    .setCorner(ModifiersBuilders.Corner.Builder().setRadius(dp(size / 2)).build()).build())
                .setClickable(ModifiersBuilders.Clickable.Builder().setId(id).setOnClick(ActionBuilders.LoadAction.Builder().build()).build())
                .build())
            .addContent(txt(label, if (size > 50) 18f else 15f, fg, bold = true))
            .build()

    private fun txt(s: String, size: Float, color: Int, bold: Boolean = false): LayoutElementBuilders.Text =
        LayoutElementBuilders.Text.Builder().setText(s).setMaxLines(1)
            .setFontStyle(LayoutElementBuilders.FontStyle.Builder().setSize(sp(size)).setColor(argb(color))
                .setWeight(if (bold) LayoutElementBuilders.FONT_WEIGHT_BOLD else LayoutElementBuilders.FONT_WEIGHT_NORMAL).build())
            .build()
}
