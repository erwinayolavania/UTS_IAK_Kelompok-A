from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import mysql.connector
from decimal import Decimal
import collections
from datetime import datetime
import requests

app = Flask(__name__)
app.secret_key = 'kunci-rahasia-yang-sangat-aman-12345'

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'supplier'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error koneksi database: {err}")
        return None

# --- Rute Login & Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn is None:
            flash('Koneksi database gagal.', 'danger')
            return render_template('login.html')

        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        account = cursor.fetchone()
        conn.close()
        
        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# --- Rute Dashboard Baru ---
@app.route('/')
def dashboard():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        return "<h1>Error: Koneksi ke database gagal.</h1>"

    cursor = conn.cursor(dictionary=True)
    
    # Hitung statistik
    cursor.execute("SELECT COUNT(*) as total FROM produk")
    total_produk = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM orders")
    total_orders = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM supplier")
    total_supplier = cursor.fetchone()['total']
    
    # Data untuk grafik stok produk
    cursor.execute("SELECT kategori, SUM(stok) as total_stok FROM produk GROUP BY kategori")
    stok_data = cursor.fetchall()
    
    # Data orders per hari untuk bulan ini - dengan semua tanggal dari 1 sampai akhir bulan
    cursor.execute("""
        WITH RECURSIVE dates(date) AS (
            SELECT DATE_FORMAT(CURDATE(), '%Y-%m-01')
            UNION ALL
            SELECT date + INTERVAL 1 DAY
            FROM dates
            WHERE date < LAST_DAY(CURDATE())
        )
        SELECT 
            DATE_FORMAT(dates.date, '%d') as day_number,
            COALESCE(COUNT(orders.id_order), 0) as order_count
        FROM dates
        LEFT JOIN orders ON DATE(orders.tanggal_order) = dates.date
        GROUP BY dates.date
        ORDER BY dates.date
    """)
    daily_orders = cursor.fetchall()
    
    # Data orders terbaru - Hitung total harga dari order_details
    cursor.execute("""
        SELECT o.id_order, o.id_distributor, o.id_retail, o.tanggal_order, o.status,
               SUM(od.jumlah_harga) as total_harga
        FROM orders o 
        LEFT JOIN order_details od ON o.id_order = od.id_order
        GROUP BY o.id_order
        ORDER BY o.id_order DESC 
        LIMIT 5
    """)
    recent_orders = cursor.fetchall()
    
    conn.close()

    # Siapkan data untuk grafik
    kategori_labels = [item['kategori'] for item in stok_data]
    stok_values = [float(item['total_stok']) for item in stok_data]
    
    # Siapkan data untuk grafik orders harian
    order_dates = [item['day_number'] for item in daily_orders]
    order_counts = [int(item['order_count']) for item in daily_orders]
    
    # Dapatkan nama bulan dalam Bahasa Indonesia
    import datetime
    month_names = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    current_month = month_names[datetime.datetime.now().month]
    current_year = datetime.datetime.now().year

    return render_template('dashboard.html', 
                         username=session['username'],
                         total_produk=total_produk,
                         total_orders=total_orders,
                         total_supplier=total_supplier,
                         kategori_labels=kategori_labels,
                         stok_values=stok_values,
                         order_dates=order_dates,
                         order_counts=order_counts,
                         recent_orders=recent_orders,
                         current_month=current_month,
                         current_year=current_year)

# --- Rute Produk (Supplier) ---
@app.route('/products')
def products():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        return "<h1>Error: Koneksi ke database gagal.</h1>"

    cursor = conn.cursor(dictionary=True)
    
    # Ambil parameter filter
    kategori_filter = request.args.get('kategori', '')
    search_query = request.args.get('search', '')
    
    # Query dasar
    query = "SELECT * FROM produk WHERE 1=1"
    params = []
    
    if kategori_filter:
        query += " AND kategori = %s"
        params.append(kategori_filter)
    
    if search_query:
        query += " AND (nama_product LIKE %s OR deskripsi LIKE %s)"
        params.extend([f'%{search_query}%', f'%{search_query}%'])
    
    query += " ORDER BY id_product"
    
    cursor.execute(query, params)
    products = cursor.fetchall()
    
    # Ambil kategori unik untuk filter
    cursor.execute("SELECT DISTINCT kategori FROM produk ORDER BY kategori")
    categories = cursor.fetchall()
    
    conn.close()

    return render_template('products.html',
                         username=session['username'],
                         products=products,
                         categories=categories,
                         kategori_filter=kategori_filter,
                         search_query=search_query)

@app.route('/orders')
def orders():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    if conn is None:
        return "<h1>Error: Koneksi ke database gagal.</h1>"

    cursor = conn.cursor(dictionary=True)
    
    # Get orders with basic info and aggregate data - ORDER BY id_order DESC
    cursor.execute("""
        SELECT o.*, 
               COUNT(od.id_order) as jumlah_item,
               SUM(od.jumlah_harga) as total_harga
        FROM orders o 
        LEFT JOIN order_details od ON o.id_order = od.id_order
        GROUP BY o.id_order
        ORDER BY o.id_order DESC
    """)
    orders = cursor.fetchall()
    
    # Get order details for each order
    order_details = {}
    for order in orders:
        cursor.execute("""
            SELECT od.*, p.nama_product, p.kategori,
                   (od.jumlah_harga / od.kuantitas) as harga_satuan
            FROM order_details od
            JOIN produk p ON od.id_product = p.id_product
            WHERE od.id_order = %s
            ORDER BY od.baris_order
        """, (order['id_order'],))
        order_details[order['id_order']] = cursor.fetchall()
    
    conn.close()

    return render_template('orders.html',
                         username=session['username'],
                         orders=orders,
                         order_details=order_details)

# --- API untuk data supplier
@app.route('/api/suppliers', methods = ['GET'])
def api_supplier():
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "Database connection failed"}), 500

    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT id_supplier, kota, nama_supplier FROM supplier")
        suppliers = cursor.fetchall()
        
        conn.close()
        
        return jsonify(suppliers)
        
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

# --- API untuk Grafik Dashboard ---
@app.route('/api/dashboard-stats')
def dashboard_stats():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    # Data stok per kategori
    cursor.execute("SELECT kategori, SUM(stok) as total_stok FROM produk GROUP BY kategori")
    stok_data = cursor.fetchall()
    
    # Data orders per status - SESUAIKAN DENGAN KOLOM STATUS BARU
    cursor.execute("SELECT status, COUNT(*) as jumlah FROM orders GROUP BY status")
    orders_data = cursor.fetchall()
    
    conn.close()

    return jsonify({
        'stok': {
            'labels': [item['kategori'] for item in stok_data],
            'values': [float(item['total_stok']) for item in stok_data]
        },
        'orders': {
            'labels': [item['status'] for item in orders_data],
            'values': [float(item['jumlah']) for item in orders_data]
        }
    })

# =============================================
# API UNTUK INTEGRASI RETAIL & DISTRIBUTOR
# =============================================

# # API Key untuk autentikasi (TIDAK DIGUNAKAN LAGI)
# API_KEYS = {
#     'retail': 'retail_api_key_12345',
#     'distributor': 'distributor_api_key_67890'
# }

# # Middleware untuk verifikasi API Key (TIDAK DIGUNAKAN LAGI)
# def require_api_key(role):
#     def decorator(f):
#         def decorated_function(*args, **kwargs):
#             api_key = request.headers.get('X-API-Key')
#             if not api_key or api_key != API_KEYS.get(role):
#                 return jsonify({'error': 'Unauthorized - Invalid API Key'}), 401
#             return f(*args, **kwargs)
#         decorated_function.__name__ = f.__name__
#         return decorated_function
#     return decorator

# --- API untuk RETAIL ---

# 1. Daftar produk yang tersedia untuk retail
@app.route('/api/retail/products', methods=['GET'])
# @require_api_key('retail') # <- Dihapus
def api_retail_products():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    # Filter hanya produk dengan stok > 0
    cursor.execute("""
        SELECT p.id_product, p.nama_product, p.kategori, p.deskripsi, 
            p.harga, p.stok, p.expired_date, p.id_supplier
        FROM produk p
        WHERE p.stok > 0
        ORDER BY p.kategori, p.nama_product
    """)


    products = cursor.fetchall()
    
    conn.close()
    
    # Convert Decimal to float for JSON serialization
    for product in products:
        if isinstance(product['harga'], Decimal):
            product['harga'] = float(product['harga'])
    
    return jsonify({'products': products})

# 2. Buat order baru dari retail
@app.route('/api/retail/orders', methods=['POST'])
def api_create_retail_order():
    data = request.get_json()
    
    id_retail = data.get('id_retail')
    id_supplier = data.get('id_supplier') 
    items = data.get('items')

    if not all([id_retail, id_supplier, items]):
        return jsonify({'error': 'Data tidak lengkap. id_retail, id_supplier, dan items wajib diisi.'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        conn.start_transaction()
        
        total_amount = 0
        total_quantity = 0
        order_items = []
        
        for item in items:
            product_id = item.get('product_id') 
            quantity = item.get('quantity', 0)
            
            if not product_id or quantity <= 0:
                conn.rollback()
                return jsonify({'error': 'Data produk tidak valid di dalam items.'}), 400

            cursor.execute("SELECT nama_product, stok, harga FROM produk WHERE id_product = %s FOR UPDATE", (product_id,))
            product = cursor.fetchone()
            
            if not product:
                conn.rollback()
                return jsonify({'error': f'Produk dengan ID {product_id} tidak ditemukan'}), 404
            
            if product['stok'] < quantity:
                conn.rollback()
                return jsonify({'error': f'Stok untuk {product["nama_product"]} tidak cukup. Tersedia: {product["stok"]}'}), 400
            
            item_total = product['harga'] * quantity
            total_amount += item_total
            total_quantity += quantity
            
            order_items.append({
                'product_id': product_id,
                'quantity': quantity,
                'total': item_total
            })

        # --- PERBAIKAN DI SINI ---
        # Hapus query ke tabel 'retail' yang tidak ada.
        # Ganti dengan mapping sederhana untuk menentukan kota tujuan.
        ASAL_PEMESAN_MAPPING = {
            1: "Surabaya",
            2: "Banyuwangi"
        }
        asal_pemesan_final = ASAL_PEMESAN_MAPPING.get(int(id_retail), "Lokasi Tidak Diketahui")

        # Query INSERT sederhana, hanya data awal
        cursor.execute("""
            INSERT INTO orders (
                tanggal_order, total_order, kuantitas_order, 
                id_retail, asal_pemesan, status,
                harga_pengiriman, total_pembayaran, id_distributor, no_resi, eta_delivery_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL)
        """, (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_amount,
            total_quantity,
            id_retail,
            asal_pemesan_final,
            'pending'
        ))
        
        order_id = cursor.lastrowid
        
        for index, item in enumerate(order_items, 1):
            cursor.execute("""
                INSERT INTO order_details (id_order, id_product, kuantitas, jumlah_harga, baris_order)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, item['product_id'], item['quantity'], item['total'], index))
        
        for item in order_items:
            cursor.execute("UPDATE produk SET stok = stok - %s WHERE id_product = %s", 
                           (item['quantity'], item['product_id']))
        
        conn.commit()
        
        return jsonify({
            'message': 'Order berhasil dibuat dan menunggu proses pengiriman.',
            'order_id': order_id
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Gagal memproses pesanan: {str(e)}'}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# 3. Cek status order dari retail
@app.route('/api/retail/orders/<int:order_id>', methods=['GET'])
def api_get_retail_order(order_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    # Dapatkan info order dasar
    cursor.execute("SELECT * FROM orders WHERE id_order = %s", (order_id,))
    order = cursor.fetchone()
    
    if not order:
        conn.close()
        return jsonify({'error': 'Order not found'}), 404
    
    # Dapatkan detail order
    cursor.execute("""
        SELECT od.*, p.nama_product, p.kategori, p.id_supplier, p.expired_date
        FROM order_details od
        JOIN produk p ON od.id_product = p.id_product
        WHERE od.id_order = %s
    """, (order_id,))
    order_details = cursor.fetchall()
    conn.close()
    
    # --- PERBAIKAN DI SINI ---
    # Ubah ke float HANYA JIKA nilainya ada (bukan None/NULL)
    if order.get('total_order') is not None and isinstance(order['total_order'], Decimal):
        order['total_order'] = float(order['total_order'])

    if order.get('harga_pengiriman') is not None and isinstance(order['harga_pengiriman'], Decimal):
        order['harga_pengiriman'] = float(order['harga_pengiriman'])

    if order.get('total_pembayaran') is not None and isinstance(order['total_pembayaran'], Decimal):
        order['total_pembayaran'] = float(order['total_pembayaran'])
    
    for detail in order_details:
        if detail.get('jumlah_harga') is not None and isinstance(detail['jumlah_harga'], Decimal):
            detail['jumlah_harga'] = float(detail['jumlah_harga'])
    
    return jsonify({
        'order': order,
        'order_details': order_details
    })

# --- API untuk DISTRIBUTOR ---

# 1. Daftar orders yang perlu dikirim
@app.route('/api/distributor/orders/pending', methods=['GET'])
# @require_api_key('distributor') # <- Dihapus
def api_pending_distributor_orders():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT o.*, p.nama_product, od.kuantitas
        FROM orders o
        JOIN order_details od ON o.id_order = od.id_order
        JOIN produk p ON od.id_product = p.id_product
        WHERE o.status = 'pending'
        ORDER BY o.tanggal_order
    """)
    
    orders = cursor.fetchall()
    conn.close()
    
    # Convert Decimal to float
    for order in orders:
        if isinstance(order['total_order'], Decimal):
            order['total_order'] = float(order['total_order'])
    
    return jsonify({'pending_orders': orders})

# 2. Update status pengiriman
@app.route('/api/distributor/orders/<int:order_id>/status', methods=['PUT'])
# @require_api_key('distributor') # <- Dihapus
def api_update_order_status(order_id):
    data = request.get_json()
    
    if not data or 'status' not in data:
        return jsonify({'error': 'Status is required'}), 400
    
    valid_statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    if data['status'] not in valid_statuses:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Update status order
        cursor.execute("UPDATE orders SET status = %s WHERE id_order = %s", 
                       (data['status'], order_id))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Order not found'}), 404
        
        conn.commit()
        
        return jsonify({'message': 'Order status updated successfully'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Failed to update order: {str(e)}'}), 500
    finally:
        conn.close()

# 3. Update tanggal pengiriman
@app.route('/api/distributor/orders/<int:order_id>/delivery', methods=['PUT'])
# @require_api_key('distributor') # <- Dihapus
def api_update_delivery_date(order_id):
    data = request.get_json()
    
    if not data or 'delivery_date' not in data:
        return jsonify({'error': 'Delivery date is required'}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Update tanggal kirim
        cursor.execute("UPDATE orders SET tanggal_kirim = %s WHERE id_order = %s", 
                       (data['delivery_date'], order_id))
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Order not found'}), 404
        
        conn.commit()
        
        return jsonify({'message': 'Delivery date updated successfully'})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'Failed to update delivery date: {str(e)}'}), 500
    finally:
        conn.close()

# 4. Daftar semua orders untuk distributor
@app.route('/api/distributor/orders', methods=['GET'])
# @require_api_key('distributor') # <- Dihapus
def api_get_distributor_orders():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    status_filter = request.args.get('status', '')
    
    query = """
        SELECT o.*, p.nama_product, od.kuantitas, od.jumlah_harga
        FROM orders o
        JOIN order_details od ON o.id_order = od.id_order
        JOIN produk p ON od.id_product = p.id_product
        WHERE 1=1
    """
    params = []
    
    if status_filter:
        query += " AND o.status = %s"
        params.append(status_filter)
    
    query += " ORDER BY o.tanggal_order DESC"
    
    cursor.execute(query, params)
    orders = cursor.fetchall()
    conn.close()
    
    # Convert Decimal to float
    for order in orders:
        if isinstance(order['total_order'], Decimal):
            order['total_order'] = float(order['total_order'])
        if isinstance(order['jumlah_harga'], Decimal):
            order['jumlah_harga'] = float(order['jumlah_harga'])
    
    return jsonify({'orders': orders})

# Pastikan retail_endpoints didefinisikan di atas fungsi ini
retail_endpoints = {
    1: "http://192.168.1.54:5000/api/orders/order-callback",
    2: "https://192.168.1.49:5000/api/orders/order-callback"
}

def send_retail_callback(id_retail, payload: dict, order_id: int) -> bool:
    """
    Kirim notifikasi callback ke Retail berdasarkan mapping 'retail_endpoints'.
    Pastikan id_retail dikonversi ke int agar cocok dengan key dict.
    """
    # Normalisasi tipe id_retail
    original = id_retail
    try:
        if isinstance(id_retail, str) and id_retail.isdigit():
            id_retail = int(id_retail)
        elif isinstance(id_retail, Decimal):
            id_retail = int(id_retail)
    except Exception:
        pass

    print(f"[DEBUG] order_id={order_id}, original_id_retail={original} ({type(original)}), normalized={id_retail}")

    callback_url = retail_endpoints.get(id_retail)

    if not callback_url:
        print(f"⏩ [Order #{order_id}] Tidak ada mapping URL untuk id_retail {original}. Callback dilewati.")
        return False

    print(f"🚀 [Order #{order_id}] Mengirim callback ke retail {id_retail} di URL: {callback_url}")
    print(f"   Payload: {payload}")

    try:
        resp = requests.post(
            callback_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if 200 <= resp.status_code < 300:
            print(f"✅ [Order #{order_id}] Callback ke retail berhasil. Status: {resp.status_code}")
            return True
        else:
            print(f"⚠️ [Order #{order_id}] Callback gagal. Status: {resp.status_code}, Detail: {resp.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ [Order #{order_id}] Error koneksi saat callback ke retail: {str(e)}")
        return False



EKSPEDISI_URLS = {
                "2": "https://denis-connectable-lawson.ngrok-free.dev/api/biaya", #KELOMPOK ARYA
                "1": "https://9026dd18c3e6.ngrok-free.app/api/quote" #KELOMPOK MANDA
            }

def _normalize_offer(raw: dict) -> dict | None:
    """
    Normalisasi response distributor ke format standar untuk retail.
    Wajib hasilkan:
    {
        id_distributor, nama_distributor, harga_pengiriman, estimasi, quote_id
    }
    """
    # id / nama distributor
    id_distributor = raw.get("id_distributor") or raw.get("distributor_id") or raw.get("id")
    nama_distributor = raw.get("nama_distributor") or raw.get("distributor_name") or raw.get("nama")

    # harga pengiriman
    harga_pengiriman = raw.get("harga_pengiriman") or raw.get("shipping_price") or raw.get("price")

    # estimasi (fallback: estimasi_pengiriman, estimasi, eta_text, eta_days)
    estimasi = raw.get("estimasi") or raw.get("estimasi_pengiriman") or raw.get("eta_text")
    if not estimasi:
        if "eta_days" in raw:
            estimasi = f"{raw['eta_days']} hari"
        elif "eta_delivery_date" in raw:
            estimasi = str(raw["eta_delivery_date"])

    # quote / resi / tracking
    quote_id = raw.get("quote_id") or raw.get("resi") or raw.get("tracking_number") or raw.get("reference")

    # Validasi minimal
    if not id_distributor or not nama_distributor or harga_pengiriman is None:
        print(f"[WARN] Respons distributor tidak lengkap: {raw}")
        return None

    try:
        harga_pengiriman = float(harga_pengiriman)
    except Exception:
        print(f"[WARN] harga_pengiriman bukan angka: {harga_pengiriman} (raw={raw})")
        return None

    return {
        "id_distributor": id_distributor,
        "nama_distributor": nama_distributor,
        "harga_pengiriman": harga_pengiriman,
        "estimasi": estimasi,
        "quote_id": quote_id,
    }

# --- API Bridge untuk Meneruskan Penawaran Pengiriman ---
@app.route('/api/pesanan_distributor', methods=['POST'])
def kirim_ke_distributor():
    data = request.get_json()
    id_order = data.get("id_order")

    if not id_order:
        return jsonify({"error": "id_order wajib diisi"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Koneksi database gagal"}), 500

    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Ambil detail order dari database untuk dikirim ke distributor
        cursor.execute("""
            SELECT 
                o.id_order, o.asal_pemesan, o.kuantitas_order, o.id_retail,
                s.kota AS kota_supplier
            FROM orders o
            JOIN order_details od ON o.id_order = od.id_order
            JOIN produk p ON od.id_product = p.id_product
            JOIN supplier s ON p.id_supplier = s.id_supplier
            WHERE o.id_order = %s
            LIMIT 1
        """, (id_order,))
        order = cursor.fetchone()

        if not order:
            return jsonify({"error": "Order tidak ditemukan"}), 404

        # 2. Siapkan payload untuk dikirim ke SEMUA API distributor
        payload_distributor = {
            "asal_pengirim": order["kota_supplier"],
            "tujuan": order["asal_pemesan"],
            "kuantitas": int(order["kuantitas_order"])
        }

        # 3. Minta penawaran dari semua distributor dan kumpulkan hasilnya
        list_penawaran_untuk_retail = []

        for nama_dist, url in EKSPEDISI_URLS.items():
            print(f"INFO: Menghubungi {nama_dist} untuk order #{id_order}")
            try:
                response = requests.post(url, json=payload_distributor, timeout=10)

                if response.status_code == 200:
                    dist_data = response.json()

                    # kalau distributor balikin list
                    if isinstance(dist_data, list):
                        for item in dist_data:
                            offer = _normalize_offer(item)
                            if offer:
                                list_penawaran_untuk_retail.append(offer)
                    else:
                        offer = _normalize_offer(dist_data)
                        if offer:
                            list_penawaran_untuk_retail.append(offer)

                else:
                    print(f"WARN: Gagal dapat penawaran dari {nama_dist}. Status: {response.status_code}")

            except requests.exceptions.RequestException as e:
                print(f"ERROR: Gagal koneksi ke {nama_dist}: {str(e)}")

        if not list_penawaran_untuk_retail:
            return jsonify({"error": "Tidak ada penawaran pengiriman yang tersedia."}), 503

        # 4. TIDAK DISIMPAN, LANGSUNG KIRIM KE RETAIL
        id_retail_val = order.get("id_retail")  # integer dari DB

        payload_untuk_retail = {
            "id_order": id_order,
            "distributor_options": list_penawaran_untuk_retail
        }

        # Kirim via helper (ada logging & timeout)
        ok = send_retail_callback(id_retail_val, payload_untuk_retail, order_id=id_order)
        if not ok:
            return jsonify({"error": f"Gagal mengirim penawaran ke retail id {id_retail_val}"}), 504

        return jsonify({
            "message": "Penawaran pengiriman berhasil diteruskan ke retail.",
            "offers_sent": len(list_penawaran_untuk_retail)
        }), 200
    
        try:
            # Kirim semua penawaran ke sistem Retail
            requests.post(retail_url, json=payload_untuk_retail, timeout=15)
            return jsonify({
                "message": "Penawaran pengiriman berhasil diteruskan ke retail.",
                "offers_sent": len(list_penawaran_untuk_retail)
            }), 200
        except requests.exceptions.RequestException as e:
            return jsonify({"error": f"Gagal mengirim penawaran ke retail: {str(e)}"}), 504

    except Exception as e:
        return jsonify({"error": f"Terjadi kesalahan internal: {str(e)}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Endpoint BARU untuk Menerima Pilihan Distributor dari Retail ---
@app.route('/api/retail/confirm-shipping', methods=['POST'])
def confirm_shipping_from_retail():
    data = request.get_json()
    
    id_order = data.get('id_order')
    quote_id = data.get('quote_id') # Retail harus mengirimkan quote_id dari penawaran yang dipilih
    id_distributor_terpilih = data.get('id_distributor')
    harga_pengiriman_terpilih = data.get('harga_pengiriman')
    estimasi_terpilih = data.get('estimasi')

    # Validasi input
    if not all([id_order, quote_id, id_distributor_terpilih, harga_pengiriman_terpilih]):
        return jsonify({"error": "Data tidak lengkap. id_order, quote_id, id_distributor, dan harga_pengiriman wajib diisi."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Koneksi database gagal"}), 500

    cursor = conn.cursor(dictionary=True)

    try:
        # Ambil total_order awal dari database
        cursor.execute("SELECT total_order FROM orders WHERE id_order = %s", (id_order,))
        order = cursor.fetchone()

        if not order:
            return jsonify({"error": "Order tidak ditemukan"}), 404

        # Hitung total pembayaran akhir
        harga_pengiriman = Decimal(harga_pengiriman_terpilih)
        total_order_sebelumnya = Decimal(order["total_order"])
        total_pembayaran = total_order_sebelumnya + harga_pengiriman

        # Update database dengan distributor yang sudah dipilih oleh retail
        cursor.execute("""
            UPDATE orders 
            SET harga_pengiriman = %s,
                total_pembayaran = %s,
                id_distributor = %s,
                eta_delivery_date = %s,
                no_resi = %s,
                status = 'processing'
            WHERE id_order = %s
        """, (
            harga_pengiriman,
            total_pembayaran,
            id_distributor_terpilih,
            estimasi_terpilih,
            quote_id, # Menggunakan quote_id sebagai no_resi awal
            id_order
        ))
        
        conn.commit()

        print(f"✅ [Order #{id_order}] Pilihan pengiriman dari retail telah dikonfirmasi dan disimpan.")
        print(f"   Distributor: ID {id_distributor_terpilih}, Harga: {harga_pengiriman}, Resi/Quote: {quote_id}")

        return jsonify({
            "message": "Pilihan pengiriman berhasil dikonfirmasi.",
            "id_order": id_order,
            "total_pembayaran": float(total_pembayaran)
        }), 200

    except Exception as e:
        conn.rollback()
        print(f"❌ Gagal mengkonfirmasi pilihan pengiriman untuk Order #{id_order}: {str(e)}")
        return jsonify({"error": f"Terjadi kesalahan internal saat update database: {str(e)}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def receive_resi_from_distributor():
    data = request.get_json()
    id_order = data.get('id_order')
    no_resi = data.get('no_resi')
    eta_delivery_date = data.get('eta_delivery_date')

    # Normalisasi status ke set {shipped, delivered, cancelled}
    incoming = (data.get('status') or 'shipped').strip().lower()
    status_map = {
        'dikirim': 'shipped',
        'shipped': 'shipped',
        'terkirim': 'delivered',
        'delivered': 'delivered',
        'cancelled': 'cancelled',
        'dibatalkan': 'cancelled',
    }
    status = status_map.get(incoming, 'shipped')

    # Validasi dasar
    if not id_order or not no_resi:
        return jsonify({"error": "Data tidak lengkap"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Update database dengan no_resi dan status
        cursor.execute("""
            UPDATE orders 
            SET no_resi = %s, 
                eta_delivery_date = %s,
                status = %s
            WHERE id_order = %s
        """, (no_resi, eta_delivery_date, status, id_order))
        
        conn.commit()
        
        # Ambil data order untuk dikirim ke retail
        cursor.execute("""
            SELECT id_order, id_retail, total_pembayaran, no_resi, eta_delivery_date
            FROM orders 
            WHERE id_order = %s
        """, (id_order,))
        order = cursor.fetchone()
        
        if order:
            # Kirim notifikasi ke retail
            payload_retail = {
                "message": "Pesanan sedang dikirim",
                "id_order": order["id_order"],
                "id_retail": order["id_retail"],
                "total_pembayaran": float(order["total_pembayaran"]) if order["total_pembayaran"] else 0,
                "no_resi": order["no_resi"],
                "eta_delivery_date": order["eta_delivery_date"]
            }
            
            # Kirim ke retail (sesuaikan URL dengan endpoint retail)
            try:
                retail_response = requests.post(
                    "https://your-retail-domain.com/api/resi",  # sesuaikan
                    json=payload_retail,
                    headers={"Content-Type": "application/json"}
                )
                print(f"Notifikasi resi ke retail: {retail_response.status_code}")
            except Exception as e:
                print(f"Gagal mengirim notifikasi resi ke retail: {str(e)}")
        
        print(f"🧾 Order {id_order} - No Resi: {no_resi}")
        print(f"🚚 Estimasi Tiba: {eta_delivery_date}")
        
        return jsonify({
            "message": "Callback resi dari distributor berhasil diterima",
            "id_order": id_order,
            "no_resi": no_resi,
            "eta_delivery_date": eta_delivery_date
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Gagal update database: {str(e)}"}), 500
    finally:
        cursor.close()
        conn.close()

# ====== di dekat konstanta lain ======
DISTRIBUTOR_MAPPING = {
    1: "PT Kuda Lumping Angkasa Tbk",              # KELOMPOK MANDA
    2: "PT Ikan Terbang Makmur Sejahtera Tbk",     # KELOMPOK ARYA
}

DISTRIBUTOR_ENDPOINTS = {
            2: "https://denis-connectable-lawson.ngrok-free.dev/api/pengiriman", #KELOMPOK ARYA
            1: "https://9026dd18c3e6.ngrok-free.app/api/shipments" #KELOMPOK MANDA
        }

# endpoint callback resi ke retail (beda dengan order-callback untuk opsi)
retail_resi_endpoints = {
            1: "http://192.168.1.54:5000/api/orders/resi",  # Alden
            2: "https://192.168.1.49:5000/api/orders/resi",  # Najla
        }

def _post_json(url: str, payload: dict, timeout=10):
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
        try:
            data = resp.json()
        except ValueError:
            data = None
        return resp.status_code, data, (data if data is not None else resp.text)
    except requests.exceptions.RequestException as e:
        return None, None, str(e)


def _kurangi_stok_dari_order(cursor, order_id: int) -> tuple[bool, str|None, list]:
    """
    Kurangi stok berdasarkan order_details. Return (ok, error_msg, barang_list_for_payload).
    barang_list_for_payload: [{id_barang, nama_barang, kuantitas}, ...]
    """
    # Ambil semua detail
    cursor.execute("""
        SELECT od.id_product, od.kuantitas, p.nama_product, p.stok
        FROM order_details od
        JOIN produk p ON p.id_product = od.id_product
        WHERE od.id_order = %s
        ORDER BY od.baris_order
    """, (order_id,))
    rows = cursor.fetchall()
    if not rows:
        return False, "Tidak ada detail barang untuk order ini", []

    # Cek stok cukup
    for r in rows:
        if r["stok"] < r["kuantitas"]:
            return False, f"Stok tidak cukup untuk produk {r['nama_product']} (minta {r['kuantitas']}, stok {r['stok']})", []

    # Kurangi stok
    for r in rows:
        cursor.execute(
            "UPDATE produk SET stok = stok - %s WHERE id_product = %s",
            (r["kuantitas"], r["id_product"])
        )

    # Susun barang_list untuk payload distributor
    barang_list = []
    for r in rows:
        barang_list.append({
            "id_barang": r["id_product"],
            "nama_barang": r["nama_product"],
            "kuantitas": int(r["kuantitas"]),
        })
    return True, None, barang_list


def _callback_resi_ke_retail(id_retail: int, payload: dict):
    url = retail_resi_endpoints.get(int(id_retail)) if id_retail is not None else None
    if not url:
        print(f"⚠️  retail_resi_endpoints belum ada untuk id_retail={id_retail}")
        return False
    sc, js, raw = _post_json(url, payload, timeout=10)
    if sc and 200 <= sc < 300:
        print(f"✅ Callback resi ke Retail {id_retail} OK ({sc})")
        return True
    print(f"⚠️  Callback resi ke Retail gagal ({sc}). Detail: {raw}")
    return False

# ====== ENDPOINT BARU: Retail memilih distributor, Supplier kirim ke distributor ======
@app.route('/api/retail/choose-distributor', methods=['POST'])
def api_retail_choose_distributor():
    """
    Body retail:
    {
      "id_order": 56,
      "id_distributor": 1
    }
    Alur:
    - Ambil order + detail
    - Kurangi stok per item
    - Kirim pembuatan pengiriman ke distributor (endpoint berbeda per id_distributor)
    - Terima no_resi, biaya, ETA -> update orders
    - total_pembayaran = total_order + harga_pengiriman
    - Callback ke retail /api/orders/resi
    """
    data = request.get_json(silent=True) or {}
    id_order = data.get("id_order")
    id_distributor = data.get("id_distributor")

    if not id_order or not id_distributor:
        return jsonify({"error": "id_order dan id_distributor wajib diisi"}), 400

    try:
        id_order = int(id_order)
        id_distributor = int(id_distributor)
    except Exception:
        return jsonify({"error": "id_order dan id_distributor harus angka"}), 400

    # Koneksi DB
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Koneksi database gagal"}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # --- Ambil info order + supplier asal + tujuan retail
        cursor.execute("""
            SELECT o.id_order, o.id_retail, o.total_order, o.asal_pemesan,
                   s.nama_supplier, s.kota AS kota_supplier
            FROM orders o
            JOIN order_details od ON od.id_order = o.id_order
            JOIN produk p ON p.id_product = od.id_product
            JOIN supplier s ON s.id_supplier = p.id_supplier
            WHERE o.id_order = %s
            LIMIT 1
        """, (id_order,))
        order = cursor.fetchone()
        if not order:
            conn.rollback()
            return jsonify({"error": f"Order {id_order} tidak ditemukan"}), 404

        # --- Kurangi stok sesuai order_details
        ok, err, barang_list = _kurangi_stok_dari_order(cursor, id_order)
        if not ok:
            conn.rollback()
            return jsonify({"error": err}), 400

        # --- Payload ke distributor
        payload_distributor = {
            "id_order": order["id_order"],
            "id_retail": order["id_retail"],
            "nama_supplier": order["nama_supplier"],
            "nama_distributor": DISTRIBUTOR_MAPPING.get(id_distributor, "Distributor Tidak Dikenal"),
            "asal_supplier": order["kota_supplier"],
            "tujuan_retail": order["asal_pemesan"],
            "barang_dipesan": barang_list
        }

        url_distributor = DISTRIBUTOR_ENDPOINTS.get(id_distributor)
        if not url_distributor:
            conn.rollback()
            return jsonify({"error": f"Endpoint distributor {id_distributor} tidak dikenali"}), 400

        print(f"🚚 Kirim ke Distributor {id_distributor} | URL: {url_distributor}")
        print(f"   Payload: {payload_distributor}")

        sc, js, raw = _post_json(url_distributor, payload_distributor, timeout=15)
        if sc is None:
            conn.rollback()
            return jsonify({"error": f"Gagal koneksi ke distributor: {raw}"}), 504

        if sc < 200 or sc >= 300:
            conn.rollback()
            return jsonify({"error": f"Distributor balas {sc}: {raw}"}), 502

        if not isinstance(js, dict):
            conn.rollback()
            return jsonify({"error": f"Distributor balas non-JSON/format tidak dikenal: {raw}"}), 502

        # --- Ambil data penting dari response distributor
        status_resp = js.get("status")
        no_resi = js.get("no_resi") or js.get("tracking_number") or js.get("resi")
        biaya_pengiriman = js.get("biaya_pengiriman") or js.get("harga_pengiriman") or 0
        eta_delivery_date = js.get("eta_delivery_date") or js.get("eta_date")
        # normalisasi biaya ke float/Decimal
        try:
            biaya_pengiriman = Decimal(str(biaya_pengiriman))
        except Exception:
            biaya_pengiriman = Decimal(0)

        if status_resp != "success" or not no_resi:
            conn.rollback()
            return jsonify({"error": f"Distributor gagal memproses. Detail: {js}"}), 502

        # --- Update orders
        # total_pembayaran = total_order + biaya_pengiriman
        total_order = Decimal(str(order["total_order"])) if order["total_order"] is not None else Decimal(0)
        total_pembayaran = total_order + biaya_pengiriman

        cursor.execute("""
            UPDATE orders
            SET id_distributor = %s,
                harga_pengiriman = %s,
                total_pembayaran = %s,
                eta_delivery_date = %s,
                no_resi = %s,
                status = %s
            WHERE id_order = %s
        """, (
            id_distributor,
            biaya_pengiriman,
            total_pembayaran,
            eta_delivery_date,
            no_resi,
            'processing',          # sekarang status 'processing' (sedang di distributor)
            id_order
        ))

        conn.commit()

        # --- Callback ke retail: kirim resi + total_pembayaran
        payload_retail = {
            "message": "Pesanan sedang dikirim ke distributor",
            "id_order": id_order,
            "id_retail": order["id_retail"],
            "total_pembayaran": float(total_pembayaran),
            "no_resi": no_resi
        }
        _callback_resi_ke_retail(order["id_retail"], payload_retail)

        return jsonify({
            "message": "Pesanan berhasil diteruskan ke distributor",
            "id_order": id_order,
            "id_distributor": id_distributor,
            "no_resi": no_resi,
            "eta_delivery_date": eta_delivery_date,
            "harga_pengiriman": float(biaya_pengiriman),
            "total_pembayaran": float(total_pembayaran),
            "status": "processing"
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Terjadi kesalahan: {str(e)}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- API Umum untuk kedua pihak ---

# Health check API
@app.route('/api/health', methods=['GET'])
def api_health():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'status': 'error', 'message': 'Database connection failed'}), 500
    
    conn.close()
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# --- Rute Product Management ---

# Route untuk halaman edit product
@app.route('/products/edit/<int:id_product>', methods=['GET', 'POST'])
def edit_product(id_product):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Koneksi database gagal.', 'danger')
        return redirect(url_for('products'))
    
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        nama_product = request.form['nama_product']
        kategori = request.form['kategori']
        deskripsi = request.form['deskripsi']
        harga = request.form['harga']
        stok = request.form['stok']
        tanggal_masuk = request.form['tanggal_masuk']
        expired_date = request.form['expired_date']
        
        # Validasi input
        if not all([nama_product, kategori, harga, stok, tanggal_masuk, expired_date]):
            flash('Semua field yang bertanda * harus diisi!', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('edit_product', id_product=id_product))
        
        try:
            query = """
                UPDATE produk 
                SET nama_product = %s, kategori = %s, deskripsi = %s, 
                    harga = %s, stok = %s, tanggal_masuk = %s, expired_date = %s
                WHERE id_product = %s
            """
            cursor.execute(query, (nama_product, kategori, deskripsi, harga, stok, tanggal_masuk, expired_date, id_product))
            conn.commit()
            conn.close()
            
            flash('Product berhasil diupdate!', 'success')
            return redirect(url_for('products'))
        
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error saat mengupdate product: {str(e)}', 'danger')
            return redirect(url_for('edit_product', id_product=id_product))
    
    # GET request
    cursor.execute("SELECT * FROM produk WHERE id_product = %s", (id_product,))
    product = cursor.fetchone()
    
    if not product:
        flash('Product tidak ditemukan!', 'danger')
        conn.close()
        return redirect(url_for('products'))
    
    conn.close()
    
    return render_template('edit_product.html',
                         username=session['username'],
                         product=product)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validasi input
        if not username or not password or not confirm_password:
            flash('Semua field harus diisi!', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Password dan Konfirmasi Password tidak cocok!', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password harus minimal 6 karakter!', 'danger')
            return render_template('register.html')
        
        conn = get_db_connection()
        if conn is None:
            flash('Koneksi database gagal.', 'danger')
            return render_template('register.html')

        cursor = conn.cursor(dictionary=True)
        
        # Cek apakah username sudah ada
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        
        if account:
            flash('Username sudah digunakan! Silakan pilih username lain.', 'danger')
            conn.close()
            return render_template('register.html')
        
        # Simpan user baru
        try:
            cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, password))
            conn.commit()
            conn.close()
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error saat registrasi: {str(e)}', 'danger')
            return render_template('register.html')
    
    return render_template('register.html')


# Route untuk delete product
@app.route('/products/delete/<int:id_product>', methods=['POST'])
def delete_product(id_product):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Koneksi database gagal.', 'danger')
        return redirect(url_for('products'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Cek apakah product ada
    cursor.execute("SELECT * FROM produk WHERE id_product = %s", (id_product,))
    product = cursor.fetchone()
    
    if not product:
        flash('Product tidak ditemukan!', 'danger')
        conn.close()
        return redirect(url_for('products'))
    
    try:
        cursor.execute("DELETE FROM produk WHERE id_product = %s", (id_product,))
        conn.commit()
        conn.close()
        
        flash(f'Product "{product["nama_product"]}" berhasil dihapus!', 'success')
    
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f'Error saat menghapus product: {str(e)}', 'danger')
    
    return redirect(url_for('products'))


# Route untuk tambah product
@app.route('/products/add', methods=['GET', 'POST'])
def add_product():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if conn is None:
        flash('Koneksi database gagal.', 'danger')
        return redirect(url_for('products'))
    
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        nama_product = request.form['nama_product']
        kategori = request.form['kategori']
        deskripsi = request.form['deskripsi']
        harga = request.form['harga']
        stok = request.form['stok']
        tanggal_masuk = request.form['tanggal_masuk']
        expired_date = request.form['expired_date']
        
        # Validasi input
        if not all([nama_product, kategori, harga, stok, tanggal_masuk, expired_date]):
            flash('Semua field yang bertanda * harus diisi!', 'danger')
            cursor.close()
            conn.close()
            return redirect(url_for('add_product'))
        
        try:
            query = """
                INSERT INTO produk (nama_product, kategori, deskripsi, harga, stok, tanggal_masuk, expired_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (nama_product, kategori, deskripsi, harga, stok, tanggal_masuk, expired_date))
            conn.commit()
            conn.close()
            
            flash('Product berhasil ditambahkan!', 'success')
            return redirect(url_for('products'))
        
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error saat menambahkan product: {str(e)}', 'danger')
            return redirect(url_for('add_product'))
    
    # GET request
    conn.close()
    
    return render_template('add_product.html',
                         username=session['username'])



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
