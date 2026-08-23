import os
import shutil
import database
import report_generator

def run_tests():
    print("=================== 啟動溫室庫存系統單元測試 ===================")
    
    db_file = database.DB_FILE
    backup_db_file = db_file + ".bak"
    
    # 1. 備份原有資料庫
    has_backup = False
    if os.path.exists(db_file):
        print(f"備份現有資料庫至 {backup_db_file}")
        shutil.copy2(db_file, backup_db_file)
        os.remove(db_file)
        has_backup = True
        
    try:
        # 2. 初始化測試資料庫
        print("步驟 1: 初始化資料庫...")
        database.init_db()
        
        # 3. 測試預設溫室是否自動建立
        print("步驟 2: 驗證預設溫室...")
        ghs = database.get_greenhouses()
        assert len(ghs) == 3, f"預期有3間預設溫室，實際取得 {len(ghs)}"
        assert ghs[0]["name"] == "研究中心"
        assert ghs[1]["name"] == "埤子頭"
        assert ghs[2]["name"] == "四湖"
        print("  - 溫室驗證成功！")
        
        # 4. 新增品項測試
        print("步驟 3: 測試新增品項...")
        res_item1 = database.add_item("有機肥料", "FERT-001", "公斤", "氮磷鉀配方肥料")
        res_item2 = database.add_item("番茄種子", "SEED-002", "公克", "高甜度聖女番茄種子")
        res_item3 = database.add_item("包裝紙箱", "BOX-003", "個", "宅配用五層瓦楞紙箱")
        
        assert res_item1["success"] is True
        assert res_item2["success"] is True
        assert res_item3["success"] is True
        
        # 測試重複品項名稱
        res_duplicate = database.add_item("有機肥料", "FERT-002", "公斤", "重複測試")
        assert res_duplicate["success"] is False
        assert "已存在" in res_duplicate["error"]
        
        items = database.get_items()
        assert len(items) == 3, f"預期有3個品項，實際取得 {len(items)}"
        print("  - 品項管理功能正常！")
        
        # 5. 測試進出庫交易邏輯 (包括庫存餘額警示)
        print("步驟 4: 測試日常進出庫與庫存檢驗...")
        gh_1_id = ghs[0]["id"]
        gh_2_id = ghs[1]["id"]
        item_fertilizer_id = items[0]["id"]
        item_seed_id = items[1]["id"]
        
        # 測試正常進庫
        res_tx1 = database.add_transaction(gh_1_id, item_fertilizer_id, "IN", 100.0, "張三", "進貨採購", "2026-07-15 10:00:00")
        assert res_tx1["success"] is True
        
        # 檢查即時庫存
        stock_level = database.get_item_stock_level(gh_1_id, item_fertilizer_id)
        assert stock_level == 100.0, f"預期庫存為 100.0，實際為 {stock_level}"
        
        # 測試正常出庫
        res_tx2 = database.add_transaction(gh_1_id, item_fertilizer_id, "OUT", 20.0, "李四", "作物施肥", "2026-07-20 14:00:00")
        assert res_tx2["success"] is True
        
        # 再次檢查庫存
        stock_level = database.get_item_stock_level(gh_1_id, item_fertilizer_id)
        assert stock_level == 80.0, f"預期庫存為 80.0，實際為 {stock_level}"
        
        # 測試出庫不足 (應攔截並回報錯誤)
        res_tx_fail = database.add_transaction(gh_1_id, item_fertilizer_id, "OUT", 90.0, "王五", "超額出庫測試", "2026-07-25 16:00:00")
        assert res_tx_fail["success"] is False
        assert "庫存不足" in res_tx_fail["error"]
        
        # 庫存應保持不變
        stock_level = database.get_item_stock_level(gh_1_id, item_fertilizer_id)
        assert stock_level == 80.0
        print("  - 進出庫驗證與安全警示攔截正常！")
        
        # 6. 測試跨月報表計算邏輯 (期初、本期進、本期出、期末)
        print("步驟 5: 測試月報表期初期末計算邏輯 (以 2026-08 為測試標的)...")
        # 2026-07-31 時，一號溫室有機肥庫存為 80.0 (期初庫存來源)
        
        # 2026-08 月份中的交易
        database.add_transaction(gh_1_id, item_fertilizer_id, "IN", 50.0, "張三", "本月補充進庫", "2026-08-05 09:00:00")
        database.add_transaction(gh_1_id, item_fertilizer_id, "OUT", 40.0, "李四", "本月施肥消耗", "2026-08-10 15:30:00")
        
        # 二號溫室種子在 2026-08 月份中的交易 (無 7 月期初)
        database.add_transaction(gh_2_id, item_seed_id, "IN", 10.0, "王五", "播種用番茄種子", "2026-08-02 11:00:00")
        
        # 2026-09 月份中的交易 (未來交易，不應影響 8 月報表)
        database.add_transaction(gh_1_id, item_fertilizer_id, "IN", 200.0, "張三", "九月新進貨", "2026-09-01 08:00:00")
        
        # 取得 2026-08 月報表資料
        report_data = database.get_monthly_report_data("2026", "08")
        
        # 應該只有 2 條記錄 (一號溫室有機肥、二號溫室番茄種子)
        assert len(report_data) == 2, f"預期有 2 條月報表數據，實際取得 {len(report_data)}"
        
        # 驗證一號溫室有機肥料的流動
        fertilizer_row = next(r for r in report_data if r["greenhouse_name"] == "研究中心" and r["item_name"] == "有機肥料")
        assert fertilizer_row["beginning_stock"] == 80.0, f"研究中心有機肥期初預期 80.0，實際 {fertilizer_row['beginning_stock']}"
        assert fertilizer_row["month_in"] == 50.0, f"研究中心有機肥進庫預期 50.0，實際 {fertilizer_row['month_in']}"
        assert fertilizer_row["month_out"] == 40.0, f"研究中心有機肥出庫預期 40.0，實際 {fertilizer_row['month_out']}"
        assert fertilizer_row["ending_stock"] == 90.0, f"研究中心有機肥期末預期 90.0，實際 {fertilizer_row['ending_stock']}"
        
        # 驗證二號溫室防番茄種子的流動
        seed_row = next(r for r in report_data if r["greenhouse_name"] == "埤子頭" and r["item_name"] == "番茄種子")
        assert seed_row["beginning_stock"] == 0.0, f"埤子頭種子期初預期 0.0，實際 {seed_row['beginning_stock']}"
        assert seed_row["month_in"] == 10.0, f"埤子頭種子進庫預期 10.0，實際 {seed_row['month_in']}"
        assert seed_row["month_out"] == 0.0, f"埤子頭種子出庫預期 0.0，實際 {seed_row['month_out']}"
        assert seed_row["ending_stock"] == 10.0, f"埤子頭種子期末預期 10.0，實際 {seed_row['ending_stock']}"
        
        print("  - 月報表期初期末流動計算完全正確！")
        
        # 7. 測試 Excel 月報表產出
        print("步驟 6: 測試 Excel 月報表產生...")
        excel_path = report_generator.generate_monthly_report("2026", "08")
        assert os.path.exists(excel_path), "Excel 報表未成功產生"
        assert excel_path.endswith(".xlsx"), "Excel 報表副檔名不正確"
        print(f"  - Excel 報表產出成功！路徑: {excel_path}")
        
        print("\n=================== 所有測試皆順利通過！ ===================")
        
    finally:
        # 8. 測試完成後還原資料庫備份
        if os.path.exists(db_file):
            os.remove(db_file)
        if has_backup:
            print(f"還原原始資料庫備份...")
            shutil.copy2(backup_db_file, db_file)
            os.remove(backup_db_file)

if __name__ == "__main__":
    run_tests()
