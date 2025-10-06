from flask import Flask, request, jsonify
import sqlite3, os

app = Flask(__name__)
DATABASE = "supplier.db"

# --- Inisialisasi DB ---
def init_db():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)  
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # tabel produk
    c.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_produk TEXT NOT NULL,
            harga REAL NOT NULL,
            stok INTEGER NOT NULL
        )
    """)

    # isi data awal produk
    c.executemany("INSERT INTO products (nama_produk, harga, stok) VALUES (?, ?, ?)", [
        ("Indomie Goreng", 3500, 100),
        ("Aqua Botol", 5000, 200),
        ("Teh Botol", 4500, 150)
    ])

    conn.commit()
    conn.close()

# --- Helper DB ---
def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute(query, args)
    rv = c.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# --- API Supplier ---
# GET daftar produk
@app.route("/api/products", methods=["GET"])
def get_products():
    rows = query_db("SELECT * FROM products")
    products = [
        {"id": r[0], "nama_produk": r[1], "harga": r[2], "stok": r[3]}
        for r in rows
    ]
    return jsonify(products)

# POST order produk
@app.route("/api/orders", methods=["POST"])
def order_product():
    data = request.get_json()
    product_id = data.get("id")
    jumlah = data.get("jumlah")

    # cek stok
    product = query_db("SELECT * FROM products WHERE id=?", (product_id,), one=True)
    if not product:
        return jsonify({"message": "Produk tidak ditemukan"}), 404

    stok = product[3]
    if jumlah > stok:
        return jsonify({"message": "Stok tidak mencukupi"}), 400

    # update stok
    query_db("UPDATE products SET stok=? WHERE id=?", (stok - jumlah, product_id))
    return jsonify({"message": f"Order berhasil, {jumlah} {product[1]} dipesan!"})

# --- Jalankan app ---
if __name__ == "__main__":
    init_db()
    app.run(port=5001, debug=True)  # jalan di port 5001