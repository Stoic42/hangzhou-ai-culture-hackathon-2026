# Step 1窄范围修复：Windows构建路径过长

- 失败退出信号：官方T5固件未能生成可烧录bin。
- 第一次诊断：日志显示`ninja: fatal: CreateProcess: 参数错误（命令行过长）`，路径嵌套超过Windows限制。
- 第二次诊断：首次`subst`在子进程结束后未保留，导致后续PowerShell找不到T盘。
- 修复边界：只在同一Windows命令进程内创建临时盘符并构建；不修改应用业务、官方SDK源码或烧录配置。
- 重跑验证：构建必须生成`.build/bin/01_Factory_Firmware_QIO_1.0.0.bin`，随后才允许烧录。
