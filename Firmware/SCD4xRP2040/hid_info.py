import hid

# RP2040のVID/PID
VID = 0x2E8A
PID = 0x000A

def main():
    print("HIDデバイス一覧:")
    print("-" * 80)
    
    devices = hid.enumerate(VID, PID)
    for device in devices:
        print(f"パス: {device['path']}")
        print(f"VID:PID: {device['vendor_id']:04X}:{device['product_id']:04X}")
        print(f"製品名: {device['product_string']}")
        print(f"メーカー: {device['manufacturer_string']}")
        print(f"シリアル: {device['serial_number']}")
        print(f"インターフェース番号: {device['interface_number']}")
        print(f"Usage Page: 0x{device['usage_page']:04X}")
        print(f"Usage: 0x{device['usage']:04X}")
        print("-" * 80)
    
    if not devices:
        print("デバイスが見つかりません")
        return
    
    # 最初のHIDインターフェースに接続
    target_device = None
    for device in devices:
        # HID Generic (Usage Page = 0xFF00) を探す
        if device['usage_page'] == 0xFF00:
            target_device = device
            break
    
    if not target_device:
        target_device = devices[0]
    
    print(f"\n接続先: {target_device['path']}")
    
    try:
        dev = hid.device()
        dev.open_path(target_device['path'])
        dev.set_nonblocking(True)
        
        print("\nデバイスに接続しました")
        print("レポートを待機中 (10秒)...")
        
        import time
        start = time.time()
        count = 0
        
        while time.time() - start < 10:
            data = dev.read(64)
            if data:
                count += 1
                print(f"\nレポート #{count} ({len(data)} bytes):")
                print("生データ (hex):", " ".join([f"{b:02X}" for b in data[:16]]))
                
                if len(data) >= 6:
                    import struct
                    co2 = struct.unpack('<H', bytes(data[0:2]))[0]
                    temp_raw = struct.unpack('<h', bytes(data[2:4]))[0]
                    hum_raw = struct.unpack('<H', bytes(data[4:6]))[0]
                    
                    temp = temp_raw / 100.0
                    hum = hum_raw / 100.0
                    
                    print(f"CO2: {co2} ppm")
                    print(f"温度: {temp:.2f} °C")
                    print(f"湿度: {hum:.2f} %")
            
            time.sleep(0.1)
        
        if count == 0:
            print("\nレポートが受信されませんでした")
            print("ヒント: デバイスがInput Reportを送信していることを確認してください")
        
        dev.close()
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == "__main__":
    main()
