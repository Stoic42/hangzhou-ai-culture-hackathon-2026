/**
 * @file builtin_assets.h
 * @brief Declarations for generated firmware assets (see tools/gen_assets.py).
 */
#ifndef BUILTIN_ASSETS_H
#define BUILTIN_ASSETS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char *json;     /**< minified rule pack v1 manifest text */
    uint32_t json_len;    /**< length in bytes, excluding NUL */
} buddy_preset_desc_t;

extern const char BUDDY_PRESET_LAST_ONE_JSON[];
extern const char BUDDY_PRESET_DO_NOW_JSON[];
extern const char BUDDY_PRESET_DECIDE_NOW_JSON[];

extern const buddy_preset_desc_t BUDDY_BUILTIN_PRESETS[];
extern const uint32_t BUDDY_BUILTIN_PRESET_COUNT;

extern const uint8_t BUDDY_FEEDBACK_PCM[];       /**< 16kHz mono 16bit */
extern const uint32_t BUDDY_FEEDBACK_PCM_SIZE;   /**< bytes */
extern const char BUDDY_FEEDBACK_SHA256[];       /**< 64 lowercase hex chars + NUL */

#ifdef __cplusplus
}
#endif

#endif /* BUILTIN_ASSETS_H */
