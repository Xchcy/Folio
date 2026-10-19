"""微信 4.1.x Config.Cipher 扫描适配（只读）。

配置布局与 XOR 掩码参考 fanyuantaier/wechatauto-replica 的 db.py，Apache-2.0。
不导入其 GUI/发送模块；候选必须通过现有数据库页 HMAC 验证。
"""
import struct

CONFIG_NAME = b"com.Tencent.WCDB.Config.Cipher"
XOR_MASK = bytes.fromhex(
    "d2c7442458020000004889442450488b"
    "450048844c2448488944254048584c24"
)


def decoded_cipher_literals(read, find):
    """通过注入的读取/搜索函数获取配置文本，便于离线验证布局。"""
    names = set(find(CONFIG_NAME))
    seen_objects = set()
    for name_addr in names:
        reference = struct.pack("<QQ", name_addr, len(CONFIG_NAME))
        for ref_addr in find(reference):
            node = read(ref_addr - 0x10, 0x50)
            if not node or len(node) < 0x40:
                continue
            if struct.unpack_from("<Q", node, 0x10)[0] != name_addr:
                continue
            if struct.unpack_from("<Q", node, 0x18)[0] != len(CONFIG_NAME):
                continue
            object_addr = struct.unpack_from("<Q", node, 0x28)[0]
            if not 0x10000 <= object_addr < 0x800000000000:
                continue
            if object_addr in seen_objects:
                continue
            seen_objects.add(object_addr)
            descriptor = read(object_addr + 0x88, 0x28)
            if not descriptor or len(descriptor) < 0x18:
                continue
            data_addr, data_length = struct.unpack_from("<QQ", descriptor, 8)
            if not (0x10000 <= data_addr < 0x800000000000 and 0 < data_length <= 1024):
                continue
            blob = read(data_addr, data_length)
            if not blob or len(blob) != data_length:
                continue
            yield bytes(value ^ XOR_MASK[i % len(XOR_MASK)] for i, value in enumerate(blob))
