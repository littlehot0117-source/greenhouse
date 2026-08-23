import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

def get_db_connection():
    if DATABASE_URL:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

def init_db():
    """初始化資料庫與建立資料表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL 建表語法
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS greenhouses (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            category VARCHAR(50) NOT NULL DEFAULT '物品類',
            sku VARCHAR(255),
            unit VARCHAR(50) NOT NULL,
            description TEXT
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            greenhouse_id INTEGER NOT NULL REFERENCES greenhouses (id) ON DELETE RESTRICT,
            item_id INTEGER NOT NULL REFERENCES items (id) ON DELETE RESTRICT,
            transaction_type VARCHAR(10) NOT NULL CHECK(transaction_type IN ('IN', 'OUT')),
            quantity NUMERIC NOT NULL CHECK(quantity > 0),
            operator VARCHAR(100) NOT NULL,
            note TEXT,
            created_at VARCHAR(50) NOT NULL
        );
        """)
        
        # 自動遷移：檢查 items 是否已有 category 欄位
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='items' AND column_name='category';")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE items ADD COLUMN category VARCHAR(50) NOT NULL DEFAULT '物品類';")
        except Exception as e:
            print("PostgreSQL Migration items category failed:", e)

        cursor.execute("SELECT COUNT(*) FROM greenhouses;")
        row = cursor.fetchone()
        count = list(row.values())[0] if row else 0
        if count == 0:
            cursor.executemany("""
            INSERT INTO greenhouses (name) VALUES (%s);
            """, [("研究中心",), ("埤子頭",), ("四湖",)])
    else:
        # SQLite 建表語法
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS greenhouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL DEFAULT '物品類',
            sku TEXT,
            unit TEXT NOT NULL,
            description TEXT
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            greenhouse_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL CHECK(transaction_type IN ('IN', 'OUT')),
            quantity REAL NOT NULL CHECK(quantity > 0),
            operator TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (greenhouse_id) REFERENCES greenhouses (id) ON DELETE RESTRICT,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE RESTRICT
        );
        """)
        
        # 自動遷移：檢查 items 是否已有 category 欄位
        try:
            cursor.execute("PRAGMA table_info(items);")
            cols = [col[1] for col in cursor.fetchall()]
            if 'category' not in cols:
                cursor.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT '物品類';")
        except Exception as e:
            print("SQLite Migration items category failed:", e)

        cursor.execute("SELECT COUNT(*) FROM greenhouses;")
        row = cursor.fetchone()
        count = row[0] if row else 0
        if count == 0:
            cursor.executemany("""
            INSERT INTO greenhouses (name) VALUES (?);
            """, [("研究中心",), ("埤子頭",), ("四湖",)])
        
    conn.commit()
    conn.close()

# --- 通用查詢小幫手 ---
def query_all(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        query = query.replace('?', '%s')
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def query_one(query, params=()):
    conn = get_db_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        query = query.replace('?', '%s')
    try:
        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

# --- 溫室管理 API ---
def get_greenhouses():
    return query_all("SELECT * FROM greenhouses ORDER BY id;")

def add_greenhouse(name):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "INSERT INTO greenhouses (name) VALUES (%s);" if DATABASE_URL else "INSERT INTO greenhouses (name) VALUES (?);"
    try:
        cursor.execute(query, (name,))
        conn.commit()
        # 取得最後新增的 id
        if DATABASE_URL:
            cursor.execute("SELECT currval(pg_get_serial_sequence('greenhouses','id'));")
            new_id = cursor.fetchone()[0]
        else:
            new_id = cursor.lastrowid
        return {"success": True, "id": new_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "溫室名稱已存在"}
    except Exception as e:
        # 處理 PostgreSQL 唯一值約束錯誤
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"success": False, "error": "溫室名稱已存在"}
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# --- 品項管理 API ---
def get_items():
    return query_all("SELECT * FROM items ORDER BY id;")

def add_item(name, sku, unit, description, category="物品類"):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    INSERT INTO items (name, category, sku, unit, description) 
    VALUES (%s, %s, %s, %s, %s);
    """ if DATABASE_URL else """
    INSERT INTO items (name, category, sku, unit, description) 
    VALUES (?, ?, ?, ?, ?);
    """
    try:
        cursor.execute(query, (name, category, sku, unit, description))
        conn.commit()
        if DATABASE_URL:
            cursor.execute("SELECT currval(pg_get_serial_sequence('items','id'));")
            new_id = list(cursor.fetchone().values())[0]
        else:
            new_id = cursor.lastrowid
        return {"success": True, "id": new_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "品項名稱已存在"}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"success": False, "error": "品項名稱已存在"}
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def update_item(item_id, name, sku, unit, description, category="物品類"):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    UPDATE items 
    SET name = %s, category = %s, sku = %s, unit = %s, description = %s 
    WHERE id = %s;
    """ if DATABASE_URL else """
    UPDATE items 
    SET name = ?, category = ?, sku = ?, unit = ?, description = ? 
    WHERE id = ?;
    """
    try:
        cursor.execute(query, (name, category, sku, unit, description, item_id))
        conn.commit()
        return {"success": True}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "品項名稱已重複"}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return {"success": False, "error": "品項名稱已重複"}
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    query_check = "SELECT COUNT(*) FROM transactions WHERE item_id = %s;" if DATABASE_URL else "SELECT COUNT(*) FROM transactions WHERE item_id = ?;"
    query_delete = "DELETE FROM items WHERE id = %s;" if DATABASE_URL else "DELETE FROM items WHERE id = ?;"
    try:
        # 檢查是否有進出庫交易紀錄參照此品項
        cursor.execute(query_check, (item_id,))
        row = cursor.fetchone()
        count = list(row.values())[0] if DATABASE_URL else row[0]
        if count > 0:
            return {"success": False, "error": "此品項已有進出庫紀錄，無法刪除"}
        
        cursor.execute(query_delete, (item_id,))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# --- 進出庫明細 API ---
def add_transaction(greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at=None):
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    query_insert = """
    INSERT INTO transactions (greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s);
    """ if DATABASE_URL else """
    INSERT INTO transactions (greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    try:
        # 如果是出庫，檢查庫存是否足夠
        if transaction_type == 'OUT':
            current_stock = get_item_stock_level(greenhouse_id, item_id)
            if current_stock < quantity:
                return {
                    "success": False, 
                    "error": f"出庫失敗：庫存不足 (目前庫存: {current_stock}，請求出庫: {quantity})"
                }
                
        cursor.execute(query_insert, (greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at))
        conn.commit()
        if DATABASE_URL:
            cursor.execute("SELECT currval(pg_get_serial_sequence('transactions','id'));")
            new_id = list(cursor.fetchone().values())[0]
        else:
            new_id = cursor.lastrowid
        return {"success": True, "id": new_id}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def get_transactions(greenhouse_id=None, item_id=None, start_date=None, end_date=None, transaction_type=None, limit=100):
    query = """
    SELECT t.*, g.name AS greenhouse_name, i.name AS item_name, i.unit AS item_unit, i.sku AS item_sku
    FROM transactions t
    JOIN greenhouses g ON t.greenhouse_id = g.id
    JOIN items i ON t.item_id = i.id
    WHERE 1=1
    """
    params = []
    
    if greenhouse_id:
        query += " AND t.greenhouse_id = ?"
        params.append(greenhouse_id)
    if item_id:
        query += " AND t.item_id = ?"
        params.append(item_id)
    if transaction_type:
        query += " AND t.transaction_type = ?"
        params.append(transaction_type)
    if start_date:
        query += " AND t.created_at >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND t.created_at <= ?"
        params.append(f"{end_date} 23:59:59")
        
    query += " ORDER BY t.created_at DESC, t.id DESC LIMIT ?;"
    params.append(limit)
    
    return query_all(query, tuple(params))

def update_transaction(tx_id, greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. 取得原有交易明細資訊
        old_tx = query_one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        if not old_tx:
            return {"success": False, "error": "找不到該筆明細紀錄"}
            
        old_gh_id = int(old_tx["greenhouse_id"])
        old_item_id = int(old_tx["item_id"])
        old_type = old_tx["transaction_type"]
        old_qty = float(old_tx["quantity"])
        
        # 2. 庫存檢查：驗證此修改是否會使庫存變為負數
        # 如果變更了溫室或品項
        if old_gh_id != greenhouse_id or old_item_id != item_id:
            # 檢查舊溫室/品項移除此筆紀錄後是否還有足夠庫存 (如果是 IN，移除會減少庫存；如果是 OUT，移除會增加庫存)
            old_net = -old_qty if old_type == 'IN' else old_qty
            old_stock = get_item_stock_level(old_gh_id, old_item_id)
            if old_stock + old_net < 0:
                return {"success": False, "error": f"修改失敗：原溫室之物品移除後將導致庫存不足 (剩餘: {old_stock + old_net})"}
                
            # 檢查新溫室/品項加入此筆紀錄後是否足夠 (如果是 OUT，新增會減少庫存)
            new_net = quantity if transaction_type == 'IN' else -quantity
            new_stock = get_item_stock_level(greenhouse_id, item_id)
            if new_stock + new_net < 0:
                return {"success": False, "error": f"修改失敗：新溫室庫存不足以支應此出庫 (目前庫存: {new_stock}，預計出庫: {quantity})"}
        else:
            # 同溫室同品項：計算庫存差額
            old_net = old_qty if old_type == 'IN' else -old_qty
            new_net = quantity if transaction_type == 'IN' else -quantity
            diff = new_net - old_net
            current_stock = get_item_stock_level(greenhouse_id, item_id)
            if current_stock + diff < 0:
                return {"success": False, "error": f"修改失敗：修改後將導致庫存不足 (剩餘: {current_stock + diff})"}
                
        # 3. 執行更新
        query = """
        UPDATE transactions
        SET greenhouse_id = %s, item_id = %s, transaction_type = %s, quantity = %s, operator = %s, note = %s, created_at = %s
        WHERE id = %s;
        """ if DATABASE_URL else """
        UPDATE transactions
        SET greenhouse_id = ?, item_id = ?, transaction_type = ?, quantity = ?, operator = ?, note = ?, created_at = ?
        WHERE id = ?;
        """
        cursor.execute(query, (greenhouse_id, item_id, transaction_type, quantity, operator, note, created_at, tx_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def delete_transaction(tx_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. 取得交易資訊
        tx = query_one("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        if not tx:
            return {"success": False, "error": "找不到該筆交易紀錄"}
            
        gh_id = int(tx["greenhouse_id"])
        item_id = int(tx["item_id"])
        tx_type = tx["transaction_type"]
        qty = float(tx["quantity"])
        
        # 2. 庫存檢查 (如果是 IN，刪除會減少庫存，需確認剩餘庫存 >= 刪除量)
        if tx_type == 'IN':
            current_stock = get_item_stock_level(gh_id, item_id)
            if current_stock - qty < 0:
                return {"success": False, "error": f"無法刪除：刪除此進庫紀錄將導致庫存不足 (目前庫存: {current_stock}，扣除: {qty})"}
                
        # 3. 執行刪除
        query = "DELETE FROM transactions WHERE id = %s;" if DATABASE_URL else "DELETE FROM transactions WHERE id = ?;"
        cursor.execute(query, (tx_id,))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# --- 庫存計算與報表 ---
def get_item_stock_level(greenhouse_id, item_id):
    """計算特定溫室內特定品項的目前庫存量"""
    query = """
    SELECT 
        SUM(CASE WHEN transaction_type = 'IN' THEN quantity ELSE -quantity END) AS stock
    FROM transactions
    WHERE greenhouse_id = ? AND item_id = ?;
    """
    row = query_one(query, (greenhouse_id, item_id))
    # 支援 SQLite (Row / dict) 與 PostgreSQL
    if row and 'stock' in row and row['stock'] is not None:
        return float(row['stock'])
    return 0.0

def get_greenhouse_stock(greenhouse_id):
    """計算特定溫室內所有品項的目前庫存"""
    # 為了兼容 PostgreSQL，GROUP BY 必須包含所有 SELECT 中非聚合的欄位
    query = """
    SELECT 
        i.id AS item_id,
        i.name AS item_name,
        i.sku AS item_sku,
        i.unit AS item_unit,
        i.description AS item_description,
        COALESCE(SUM(CASE WHEN t.transaction_type = 'IN' THEN t.quantity ELSE -t.quantity END), 0) AS current_stock
    FROM items i
    LEFT JOIN transactions t ON t.item_id = i.id AND t.greenhouse_id = ?
    GROUP BY i.id, i.name, i.sku, i.unit, i.description
    HAVING COALESCE(SUM(CASE WHEN t.transaction_type = 'IN' THEN t.quantity ELSE -t.quantity END), 0) > 0
    ORDER BY i.name;
    """
    return query_all(query, (greenhouse_id,))

def get_monthly_report_data(year, month):
    """
    計算某月份各溫室各品項的月流動報表
    """
    try:
        y = int(year)
        m = int(month)
        if m == 12:
            next_y, next_m = y + 1, 1
        else:
            next_y, next_m = y, m + 1
        month_start = f"{y:04d}-{m:02d}-01 00:00:00"
        month_end = f"{next_y:04d}-{next_m:02d}-01 00:00:00"
    except ValueError:
        month_start = f"{year}-{month}-01 00:00:00"
        month_end = f"{year}-{month}-31 23:59:59"
        
    query_precise = """
    WITH prev_transactions AS (
        SELECT 
            greenhouse_id, 
            item_id, 
            SUM(CASE WHEN transaction_type = 'IN' THEN quantity ELSE -quantity END) AS prev_qty
        FROM transactions
        WHERE created_at < ?
        GROUP BY greenhouse_id, item_id
    ),
    curr_transactions AS (
        SELECT 
            greenhouse_id, 
            item_id,
            SUM(CASE WHEN transaction_type = 'IN' THEN quantity ELSE 0 END) AS in_qty,
            SUM(CASE WHEN transaction_type = 'OUT' THEN quantity ELSE 0 END) AS out_qty
        FROM transactions
        WHERE created_at >= ? AND created_at < ?
        GROUP BY greenhouse_id, item_id
    )
    SELECT 
        g.id AS greenhouse_id,
        g.name AS greenhouse_name,
        i.id AS item_id,
        i.name AS item_name,
        i.sku AS item_sku,
        i.unit AS item_unit,
        COALESCE(p.prev_qty, 0.0) AS beginning_stock,
        COALESCE(c.in_qty, 0.0) AS month_in,
        COALESCE(c.out_qty, 0.0) AS month_out,
        (COALESCE(p.prev_qty, 0.0) + COALESCE(c.in_qty, 0.0) - COALESCE(c.out_qty, 0.0)) AS ending_stock
    FROM items i
    CROSS JOIN greenhouses g
    LEFT JOIN prev_transactions p ON p.greenhouse_id = g.id AND p.item_id = i.id
    LEFT JOIN curr_transactions c ON c.greenhouse_id = g.id AND c.item_id = i.id
    WHERE COALESCE(p.prev_qty, 0.0) != 0.0 
       OR COALESCE(c.in_qty, 0.0) != 0.0 
       OR COALESCE(c.out_qty, 0.0) != 0.0
    ORDER BY g.id, i.name;
    """
    
    # 執行查詢
    return query_all(query_precise, (month_start, month_start, month_end))

# 初始化
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
    print("Greenhouses:", get_greenhouses())
