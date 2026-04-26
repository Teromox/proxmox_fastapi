import sqlite3

con = sqlite3.connect('db.db')
cur = con.cursor()

# CREATE TABLE 
"""
ext_port integer primary key
ip string
in_port integer
"""
cur.execute('''CREATE TABLE IF NOT EXISTS nat_table
                (ext_port integer primary key, ip text, in_port integer)''')

con.commit()
con.close()