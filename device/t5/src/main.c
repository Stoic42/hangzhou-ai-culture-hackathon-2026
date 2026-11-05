/**
 * @file main.c
 * @brief T5 entry for the offline preset buddy firmware.
 */
#include "tuya_cloud_types.h"

#include "board_com_api.h"
#include "lv_vendor.h"
#include "lvgl.h"
#include "tal_api.h"
#include "tkl_output.h"

#include "buddy_ui.h"

void user_main(void)
{
    tal_log_init(TAL_LOG_LEVEL_DEBUG, 4096, (TAL_LOG_OUTPUT_CB)tkl_log_output);
    tal_sw_timer_init();
    board_register_hardware();

    buddy_audio_init();

    lv_vendor_init(DISPLAY_NAME);
    lv_vendor_disp_lock();
    buddy_app_init();
    lv_vendor_disp_unlock();
    lv_vendor_start(THREAD_PRIO_0, 1024 * 8);
}

#if OPERATING_SYSTEM == SYSTEM_LINUX
void main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    user_main();
    while (1) {
        tal_system_sleep(500);
    }
}
#else
static THREAD_HANDLE s_app_thread = NULL;

static void app_thread(void *arg)
{
    (void)arg;
    user_main();
    tal_thread_delete(s_app_thread);
    s_app_thread = NULL;
}

void tuya_app_main(void)
{
    THREAD_CFG_T config = {
        .stackDepth = 1024 * 4,
        .priority = THREAD_PRIO_1,
        .thrdname = "tuya_app_main",
    };
    tal_thread_create_and_start(&s_app_thread, NULL, NULL, app_thread, NULL, &config);
}
#endif
