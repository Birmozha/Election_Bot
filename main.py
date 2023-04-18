import sqlite3
import os

from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

users = {'a1': {'password': 'pass1'},
         'a2': {'password': 'pass2'}}

class User(UserMixin):
    pass

@login_manager.user_loader
def userLoader(username):
    if username not in users:
        return
    user = User()
    user.id = username
    return user




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and password == users[username]['password']:
            user = User()
            user.id = username
            login_user(user)
            return redirect('/index')
        return 'Invalid'
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')



@app.route('/bot-flow')
@login_required
def show_flow():
    tree = []
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        null = cur.execute("""SELECT qid FROM tree WHERE pid IS null""").fetchone()[0]
        level_id = cur.execute("""WITH RECURSIVE
                        cte(qid, level) AS (
                            VALUES((?), 0)
                            UNION ALL
                            SELECT tree.qid, cte.level+1
                            FROM tree JOIN cte ON tree.pid = cte.qid
                            ORDER BY 2 DESC)
                            SELECT level, qid FROM cte""", (null, )).fetchall()
        
        level_id = [el for el in level_id]
        tree = []
        for el in level_id:
            temp = cur.execute("""SELECT data.text, tree.properties FROM data, tree WHERE data.id is (?) AND tree.qid IS (?)""", (el[1], el[1])).fetchone()
            temp = (temp[0], tuple(temp[1].split(', ')))
            tree.append((el[0]+1, temp[0], el[1], temp[1])) # (УРОВЕНЬ, ТЕКСТ, НОМЕР, СВОЙСТВА)
    return render_template('botFlow.html', tree=tree)

@app.route('/')
@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/info-tree')
@login_required
def info_tree():
    tree = []
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        null = cur.execute("""SELECT qid FROM tree WHERE pid IS null""").fetchone()[0]
        cats = cur.execute("""SELECT qid FROM tree WHERE pid is (?)""", (null, )).fetchall()
        level_id = cur.execute("""WITH RECURSIVE
                        cte(qid, level) AS (
                            VALUES((?), 0)
                            UNION ALL
                            SELECT tree.qid, cte.level+1
                            FROM tree JOIN cte ON tree.pid = cte.qid
                            ORDER BY 2 DESC)
                            SELECT level, qid FROM cte""", (cats[0][0], )).fetchall()
        
        level_id = [el for el in level_id]
        tree = []
        for el in level_id:
            temp = cur.execute("""SELECT data.text, tree.properties FROM data, tree WHERE data.id is (?) AND tree.qid IS (?)""", (el[1], el[1])).fetchone()
            temp = (temp[0], tuple(temp[1].split(', ')))
            tree.append((el[0]+1, temp[0], el[1], temp[1])) # (УРОВЕНЬ, ТЕКСТ, НОМЕР, СВОЙСТВА)
    return render_template('infoTree.html', tree=tree)

@app.route('/info-tree/<int:id>/change', methods=['POST', 'GET'])
@login_required
def changeLeaf(id):
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        props = cur.execute("""SELECT prop FROM properties WHERE category is (?) """, (2, )).fetchone()[0].split(' | ')
        properties = []
        for el in props:
            if el != '<button>':
                temp = (el, cur.execute("""SELECT text FROM properties_text WHERE prop is (?) """, (el, )).fetchone()[0])
                properties.append(temp)
        current_property = (cur.execute("""SELECT properties FROM tree WHERE qid IS (?) """, (id, )).fetchone()[0])
        current_property = (current_property, (cur.execute("""SELECT text FROM properties_text WHERE prop IS (?) """, (current_property, )).fetchone()[0]))
        data = cur.execute("""SELECT text FROM data WHERE id IS (?)""", (id, )).fetchone()
        
    if request.method == "POST":
        text = request.form['text']
        property = None
        try:
            if request.form['button-type'] and request.form['button-type'] != '-':
                property = request.form['button-type']
        except KeyError:
            pass
        with sqlite3.connect('database/data.db') as db:
            cur = db.cursor()
            db.execute("""BEGIN TRANSACTION""")
            cur.execute("""UPDATE data
                            SET  (text)
                            = ((?))
                            WHERE id IS (?) ;
                            """, (text, id))
            if property:
                cur.execute("""UPDATE tree
                                SET  (properties)
                                = ((?))
                                WHERE qid IS (?) ;
                                """, (property, id))
            db.execute("""END TRANSACTION""")
        return redirect('/info-tree')
    
    return render_template('changeLeaf.html', data=data, properties=properties, current_property=current_property, id=id)




@app.route('/info-tree/delete/<int:id>')
@login_required
def deleteLeaf(id):
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        db.execute("""PRAGMA foreign_keys = ON""")
        db.execute("""BEGIN TRANSACTION""")
        cur.execute("""DELETE FROM tree WHERE qid is (?) """, (id, ))
        db.execute("""END TRANSACTION""")
    return redirect('/info-tree')

@app.route('/complain-tree/delete/<int:id>')
@login_required
def deleteComplainLeaf(id):
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        db.execute("""PRAGMA foreign_keys = ON""")
        db.execute("""BEGIN TRANSACTION""")
        cur.execute("""DELETE FROM tree WHERE qid is (?) """, (id, ))
        db.execute("""END TRANSACTION""")
    return redirect('/complain-tree')


@app.route('/info-tree/add', methods=['POST', 'GET'])
@login_required
def addLeaf():
    tree = []
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        null = cur.execute("""SELECT qid FROM tree WHERE pid IS null""").fetchone()[0]
        cats = cur.execute("""SELECT qid FROM tree WHERE pid is (?)""", (null, )).fetchall()
        level_id = cur.execute("""WITH RECURSIVE
                        cte(qid, level) AS (
                            VALUES((?), 0)
                            UNION ALL
                            SELECT tree.qid, cte.level+1
                            FROM tree JOIN cte ON tree.pid = cte.qid
                            ORDER BY 2 DESC)
                            SELECT level, qid FROM cte""", (cats[0][0], )).fetchall()
        
        level_id = [el for el in level_id]
        tree = []
        for el in level_id:
            temp = cur.execute("""SELECT data.text, tree.properties FROM data, tree WHERE data.id is (?) AND tree.qid IS (?)""", (el[1], el[1])).fetchone()
            temp = (temp[0], tuple(temp[1].split(', ')))
            tree.append((el[0]+1, temp[0], el[1], temp[1])) # (УРОВЕНЬ, ТЕКСТ, НОМЕР, СВОЙСТВА)
        props = cur.execute("""SELECT prop FROM properties WHERE category is (?) """, (cats[0][0], )).fetchone()[0].split(' | ')
        properties = []
        for el in props:
            temp = (el, cur.execute("""SELECT text FROM properties_text WHERE prop is (?) """, (el, )).fetchone()[0])
            properties.append(temp)
        
    if request.method == 'POST':
        text = request.form['text']
        property = request.form['button-type']
        pid = request.form['pid']
        if not text:
            return redirect('/info-tree/add')
        elif property == '--Выберите вид элемента--':
            return redirect('/info-tree/add')
        elif pid == '--Выберите элемент-родитель--':
            return redirect('/info-tree/add')

        with sqlite3.connect('database/data.db') as db:
            cur = db.cursor()
            cur.execute("""INSERT INTO tree (pid, properties)
                        VALUES ((?), (?))
                        """, (pid, property))
            cur.execute("""INSERT INTO data (text)
                        VALUES ((?))
                        """, (text, ))
            
        return redirect('/info-tree/add')
    return render_template('addLeaf.html', tree=tree, properties=properties)


@app.route('/complain-tree/<int:id>/change', methods=['POST', 'GET'])
@login_required
def changeComplainTree(id):
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        props = cur.execute("""SELECT prop FROM properties WHERE category is (?) """, (17, )).fetchone()[0].split(' | ')
        properties = []
        for el in props:
            temp = (el, cur.execute("""SELECT text FROM properties_text WHERE prop is (?) """, (el, )).fetchone()[0])
            properties.append(temp)
        current_property = (cur.execute("""SELECT properties FROM tree WHERE qid IS (?) """, (id, )).fetchone()[0])
        current_property = (current_property, (cur.execute("""SELECT text FROM properties_text WHERE prop IS (?) """, (current_property, )).fetchone()[0]))
        data = cur.execute("""SELECT text FROM data WHERE id IS (?)""", (id, )).fetchone()
        
    if request.method == "POST":
        text = request.form['text']
        property = None
        try:
            if request.form['button-type'] and request.form['button-type'] != '-':
                property = request.form['button-type']
        except KeyError:
            pass
        with sqlite3.connect('database/data.db') as db:
            cur = db.cursor()
            db.execute("""BEGIN TRANSACTION""")
            cur.execute("""UPDATE data
                            SET  (text)
                            = ((?))
                            WHERE id IS (?) ;
                            """, (text, id))
            if property:
                cur.execute("""UPDATE tree
                                SET  (properties)
                                = ((?))
                                WHERE qid IS (?) ;
                                """, (property, id))
            db.execute("""END TRANSACTION""")
        return redirect('/complain-tree')
    
    return render_template('changeComplainLeaf.html', data=data, properties=properties, current_property=current_property, id=id)


@app.route('/complain-tree')
@login_required
def complain_tree():
    tree = []
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        null = cur.execute("""SELECT qid FROM tree WHERE pid IS null""").fetchone()[0]
        cats = cur.execute("""SELECT qid FROM tree WHERE pid is (?)""", (null, )).fetchall()
        level_id = cur.execute("""WITH RECURSIVE
                        cte(qid, level) AS (
                            VALUES((?), 0)
                            UNION ALL
                            SELECT tree.qid, cte.level+1
                            FROM tree JOIN cte ON tree.pid = cte.qid
                            ORDER BY 2 DESC)
                            SELECT level, qid FROM cte""", (cats[1][0], )).fetchall()
        
        level_id = [el for el in level_id]
        tree = []
        for el in level_id:
            temp = cur.execute("""SELECT data.text, tree.properties FROM data, tree WHERE data.id is (?) AND tree.qid IS (?)""", (el[1], el[1])).fetchone()
            temp = (temp[0], tuple(temp[1].split(', ')))
            tree.append((el[0]+1, temp[0], el[1], temp[1])) # (УРОВЕНЬ, ТЕКСТ, НОМЕР, СВОЙСТВА)
    return render_template('complainTree.html', tree=tree)

@app.route('/complain-tree/add', methods=['POST', 'GET'])
@login_required
def addComplainLeaf():
    tree = []
    with sqlite3.connect('database/data.db') as db:
        cur = db.cursor()
        null = cur.execute("""SELECT qid FROM tree WHERE pid IS null""").fetchone()[0]
        cats = cur.execute("""SELECT qid FROM tree WHERE pid is (?)""", (null, )).fetchall()
        level_id = cur.execute("""WITH RECURSIVE
                        cte(qid, level) AS (
                            VALUES((?), 0)
                            UNION ALL
                            SELECT tree.qid, cte.level+1
                            FROM tree JOIN cte ON tree.pid = cte.qid
                            ORDER BY 2 DESC)
                            SELECT level, qid FROM cte""", (cats[1][0], )).fetchall()
        
        level_id = [el for el in level_id]
        tree = []
        for el in level_id:
            temp = cur.execute("""SELECT data.text, tree.properties FROM data, tree WHERE data.id is (?) AND tree.qid IS (?)""", (el[1], el[1])).fetchone()
            temp = (temp[0], tuple(temp[1].split(', ')))
            tree.append((el[0]+1, temp[0], el[1], temp[1])) # (УРОВЕНЬ, ТЕКСТ, НОМЕР, СВОЙСТВА)
        
        props = cur.execute("""SELECT prop FROM properties WHERE category is (?) """, (cats[1][0], )).fetchone()[0].split(' | ')
        properties = []
        for el in props:
            temp = (el, cur.execute("""SELECT text FROM properties_text WHERE prop is (?) """, (el, )).fetchone()[0])
            properties.append(temp)
            
        
    if request.method == 'POST':
        text = request.form['text']
        property = request.form['block-type']
        pid = request.form['pid']
        if not text:
            return redirect('/complain-tree/add')
        elif property == '--Выберите вид элемента--':
            return redirect('/complain-tree/add')
        elif pid == '--Выберите элемент-родитель--':
            return redirect('/complain-tree/add')

        with sqlite3.connect('database/data.db') as db:
            cur = db.cursor()
            cur.execute("""INSERT INTO tree (pid, properties)
                        VALUES ((?), (?))
                        """, (pid, property))
            cur.execute("""INSERT INTO data (text)
                        VALUES ((?))
                        """, (text, ))
            
        return redirect('/complain-tree/add')
    return render_template('addComplainLeaf.html', tree=tree, properties=properties)


if __name__ == '__main__':
    app.run(debug=True)
    