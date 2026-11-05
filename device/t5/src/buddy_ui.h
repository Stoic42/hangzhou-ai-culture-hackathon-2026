/**
 * @file buddy_ui.h
 * @brief Offline preset buddy UI entry (LVGL screens, home/detail/generate/game).
 */
#ifndef BUDDY_UI_H
#define BUDDY_UI_H

#ifdef __cplusplus
extern "C" {
#endif

/** Audio codec init; call before lv_vendor_init. */
void buddy_audio_init(void);

/** Boot: parse & validate embedded presets, verify builtin resources, show home. */
void buddy_app_init(void);

#ifdef __cplusplus
}
#endif

#endif /* BUDDY_UI_H */
