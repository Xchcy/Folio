# 内置微信读取组件

来自 https://github.com/huohuoer/wechat-cli ，版本 0.2.4，上游基线 a3789232d4f79bf0b30634d9dadbce71e4acd601，Apache-2.0；完整许可见 LICENSE-wechat-cli。

沿用本项目此前已修复的 Windows ctypes 指针类型、进程列表本地化和微信 4.1 Config.Cipher 兼容。后者布局参考 https://github.com/fanyuantaier/wechatauto-replica 的 db.py（Apache-2.0），归属说明保留在 keys/wcdb_config.py。未接入其发送或 GUI 功能。

此目录用于本项目本机只读接入及命令行初始化，保留上游说明与许可证；本次整合未更改 vendor 中的原始 Python 模块。初始化由用户主动执行，网页读取复用已有 ~/.wechat-cli 配置和密钥，不会自动执行初始化。
