/**
 * @file ui_text.h
 * @brief All user-facing Chinese UI strings.
 *
 * tools/gen_assets.py scans this file for CJK glyphs and bakes every
 * needed glyph into the generated Noto Sans SC subset font, so any new string
 * added here must be followed by re-running gen_assets.py.
 */
#ifndef UI_TEXT_H
#define UI_TEXT_H

#define UI_APP_TITLE "当代妖怪收容所"
#define UI_HOME_INDEX_FMT "本地妖怪  %d/%d"
#define UI_HOME_PLAY "点按开局"
#define UI_HOME_HINT "左右换妖 · 长按详情"
#define UI_INVITE "再刷一条？"
#define UI_INVITE_HINT "点按接受 · 长按拒绝"
#define UI_REFUSE_HINT "再长按一次就能放下"
#define UI_REFUSE_FIRST "继续长按拒绝它"
#define UI_REFUSED_FMT "已拒绝 %d / 3"
#define UI_ENDED "本局结束"
#define UI_TAG_FMT "#%s"
#define UI_LOCAL_READY "本地状态：可离线游玩"
#define UI_BTN_GENERATE "生成搭子"
#define UI_BTN_BACK "返回"
#define UI_DETAIL_TITLE "妖怪详情"
#define UI_DETAIL_NAME "名称"
#define UI_DETAIL_PERSONALITY "性格"
#define UI_DETAIL_GAMEPLAY "玩法简介"
#define UI_DETAIL_TAGS "主题标签"
#define UI_DETAIL_STATUS "本地状态"
#define UI_GEN_TITLE "生成搭子"
#define UI_GEN_UNAVAILABLE "离线模式暂不可用\n生成搭子需要网络\n后续版本开放"
#define UI_GAME_REMAINING_FMT "剩余 %d 秒"
#define UI_GAME_BACK "返回"
#define UI_OUTCOME_ESCAPED "破解成功"
#define UI_OUTCOME_CARRIED "被搭子带跑"
#define UI_BTN_RESTART "再玩一局"
#define UI_VALIDATION_FAILED "规则包校验失败，无法开局"
#define UI_RESOURCE_FAILED "内置资源校验失败，无法开局"

#endif /* UI_TEXT_H */
