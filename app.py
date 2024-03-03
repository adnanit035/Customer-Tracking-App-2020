import io
import os
import shutil

import cv2
from flask import Flask, render_template, redirect, session, flash, Response, abort
from flask_sqlalchemy import SQLAlchemy, request, Model
from datetime import datetime
import json
from camera import VideoCamera
import keyboard
import copy

from scipy.spatial.distance import cosine
import mtcnn
from keras.models import load_model
from utils import *

import model_trainer

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
isImagesSaved = False
isImagesUpdated = False
selectedCustomerId = 0

app = Flask(__name__)
app.secret_key = 'super-secret-key'

with open('templates/config.json', 'r') as c:
    params = json.load(c)['params']

app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:@localhost/db_customer_tracking"
db = SQLAlchemy(app)


class tbl_admin(db.Model):
    sno = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), nullable=False)
    password = db.Column(db.String(25), nullable=False)


class tbl_custmers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False)
    customer_name = db.Column(db.String(80), nullable=False)
    customer_phoneNo = db.Column(db.String(12), nullable=False)
    customer_address = db.Column(db.String(120), nullable=False)
    customer_temperature = db.Column(db.FLOAT, nullable=False)
    date_time = db.Column(db.String(12), nullable=True)


class tbl_customers_tracking(db.Model):
    '''visit_id, customer_id, customer_temperature, visit_date_time'''
    visit_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, nullable=False)
    customer_temperature = db.Column(db.FLOAT, nullable=False)
    visit_date_time = db.Column(db.String(12), nullable=True)


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/', methods=['GET', 'POST'])
def recognize_customer():
    try:
        os.remove("templates/customer.txt")
    except:
        pass
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        if (request.method == 'POST'):
            '''Add visit entry to the database'''
            '''visit_id, customer_id, customer_temperature, visit_date_time'''
            customer_id = int(request.form.get('cust_id'))
            customer_temperature = request.form.get('temperature')

            if float(customer_temperature) > 37.5:
                flash("Warning! Temperature is greater than 37.5...Customer not allowed to enter", "danger")
                flash("Un-Success! Customer visit entry not added into database...", "warning")
                return render_template('recognize_customer.html')

            entry = tbl_customers_tracking(customer_id=customer_id, customer_temperature=customer_temperature, visit_date_time=datetime.now())
            db.session.add(entry)
            db.session.commit()
            flash("Success! Customer visit entry added.", "Success")
            try:
                os.remove('templates/customer.txt')
            except:
                pass
        return render_template('recognize_customer.html')

    if request.method == 'POST':
        admin_username = request.form.get('username')
        admin_password = request.form.get('password')
        if admin_username.__eq__(admin_user.username) and admin_password.__eq__(admin_user.password):
            session['admin_user'] = admin_username
            return render_template('recognize_customer.html')

    return render_template('login.html')


@app.route('/add-customer', methods=['GET', 'POST'])
def register_customer():
    customers = tbl_custmers.query.all()
    new_customer_id = 0
    if len(customers) == 0:
        new_customer_id = 1
    else:
        for c_id in customers:
            new_customer_id = int(c_id.customer_id + 1)

    global isImagesSaved

    isLoggedIn = False
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        isLoggedIn = True

    if isLoggedIn:
        if (request.method == 'POST'):
            '''Add entry to the database'''
            ''''customer_id, customer_name, customer_phoneNo, customer_address, customer_temperature, date_time'''
            customer_id = new_customer_id
            fname = request.form.get('first_name')
            lname = request.form.get('last_name')
            phone = request.form.get('phone_no')
            address = request.form.get('address')
            temperature = request.form.get('temperature')

            if not isImagesSaved:
                flash("Un-Success! Please First Capture Customer Images...", "warning")
                return render_template('add_customer.html')

            if float(temperature) > 37.5:
                subdirectories = [os.path.join('dataset', f) for f in os.listdir('dataset')]
                for dir in subdirectories:
                    try:
                        dir_id = int(dir.split('\\')[1])
                        if dir_id == new_customer_id:
                            shutil.rmtree(dir)
                    except:
                        pass
                isImagesSaved = False

                flash("Warning! Temperature is less than 37.5...Customer not allowed to enter", "danger")
                flash("Un-Success! Customer not Registered...", "warning")
                return render_template('add_customer.html')

            entry = tbl_custmers(customer_id=customer_id, customer_name=fname + ' ' + lname, customer_phoneNo=phone, customer_address=address,
                                 customer_temperature=temperature, date_time=datetime.now())
            db.session.add(entry)
            db.session.commit()
            flash("Success! Customer Registered Successfully", "Success")
            # training model again with new saved faces
            if not model_trainer.train_model():
                flash("Exception Occur while training model", "danger")
                subdirectories = [os.path.join('dataset', f) for f in os.listdir('dataset')]
                for dir in subdirectories:
                    try:
                        dir_id = int(dir.split('\\')[1])
                        if dir_id == new_customer_id:
                            shutil.rmtree(dir)
                    except:
                        pass

                try:
                    selected_customer = tbl_custmers.query.filter_by(customer_id=int(new_customer_id)).first()
                    db.session.delete(selected_customer)
                    db.session.commit()
                except:
                    print('error: record from tbl_customers not deleted...')

                isImagesSaved = False
            else:
                isImagesSaved = False
        return render_template('add_customer.html')
    else:
        return render_template('login.html')


@app.route('/manage-customers')
def manage_customers():
    isLoggedIn = False
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        isLoggedIn = True

    if isLoggedIn:
        customers = tbl_custmers.query.all()
        return render_template('manage_customers.html', customers=customers)
    else:
        return render_template('login.html')


@app.route('/edit-customer-' + '<int:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    global selectedCustomerId, isImagesUpdated
    selectedCustomerId = customer_id
    isLoggedIn = False
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        isLoggedIn = True

    if isLoggedIn:
        selected_customer = tbl_custmers.query.filter_by(customer_id=customer_id).first()
        if (request.method == 'POST'):
            '''Add entry to the database'''
            ''''customer_id, customer_name, customer_phoneNo, customer_address, customer_temperature, date_time'''

            selected_customer.customer_id = customer_id
            selected_customer.customer_name = request.form.get('first_name') + ' ' + request.form.get('last_name')
            selected_customer.customer_phoneNo = request.form.get('phone_no')
            selected_customer.customer_address = request.form.get('address')
            selected_customer.customer_temperature = request.form.get('temperature')
            db.session.commit()
            if isImagesUpdated:
                model_trainer.train_model()
                isImagesUpdated = False
            return redirect('/manage-customers')
        return render_template('edit_customer.html', selected_customer=selected_customer)
    else:
        return render_template('login.html')


@app.route('/delete-customer-' + '<int:customer_id>', methods=['GET', 'POST'])
def delete_customer(customer_id):
    isLoggedIn = False
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        isLoggedIn = True

    if isLoggedIn:
        try:
            selected_customer = tbl_custmers.query.filter_by(customer_id=int(customer_id)).first()
            db.session.delete(selected_customer)
            db.session.commit()
        except:
            print('error: record from tbl_customers not deleted...')
        try:
            stmt = tbl_customers_tracking.__table__.delete().where(tbl_customers_tracking.customer_id == customer_id)
            db.session.execute(stmt)
            db.session.commit()
        except:
            print('error: record from tbl_customer_tracking not deleted...')

        subdirectories = [os.path.join('dataset', f) for f in os.listdir('dataset')]
        for dir in subdirectories:
            try:
                dir_id = int(dir.split('\\')[1])
                if dir_id == customer_id:
                    shutil.rmtree(dir)
            except:
                pass

        return redirect('/manage-customers')
    else:
        return render_template('login.html')


@app.route('/tracking-activities')
def activities():
    isLoggedIn = False
    admin_user = tbl_admin.query.all()[0]
    if 'admin_user' in session and session['admin_user'] == admin_user.username:
        isLoggedIn = True

    if isLoggedIn:
        customers = tbl_custmers.query.all()
        customers_activities = tbl_customers_tracking.query.all()
        return render_template('tracking_activities.html', customers=customers, customer_visits=customers_activities)
    else:
        return render_template('login.html')


@app.route('/logout')
def logout():
    # remove the username from the session if it is there
    session.pop('admin_user', None)
    return redirect('/login')


def capture_image(camera):
    font = cv2.FONT_HERSHEY_SIMPLEX

    customers = tbl_custmers.query.all()
    new_customer_id = 0
    if len(customers) == 0:
        new_customer_id = 1
    else:
        for c_id in customers:
            new_customer_id = int(c_id.customer_id + 1)

    faceCascade = cv2.CascadeClassifier('Cascades/haarcascade_frontalface_default.xml')
    while True:
        global isImagesSaved
        img = camera.get_Image()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        image = copy.copy(img)
        faces = faceCascade.detectMultiScale(gray, 1.3, 5)
        cv2.putText(img, "'F4': Capture Image: ", (10, 340), font, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

        for (x, y, w, h) in faces:
            # Press 'F4' to Capture Image for Customer dataset
            if keyboard.is_pressed('F4'):
                if faces is not None:
                    cwd = os.getcwd()
                    dir = os.path.join(cwd, "dataset", str(new_customer_id))
                    if not os.path.exists(dir):
                        os.mkdir(dir)
                        cv2.imwrite("dataset/" + str(new_customer_id) + "/" + str(new_customer_id) + ".jpg", image)
                        isImagesSaved = True

            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if isImagesSaved:
            cv2.putText(img, 'Succeeded! Customer Images Saved...', (80, 60), font, 0.8, (255, 0, 0), 2, cv2.LINE_AA)
            # break

        ret, jpg = cv2.imencode('.jpg', img)
        frame = jpg.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


def capture_image2(camera):
    global selectedCustomerId
    font = cv2.FONT_HERSHEY_SIMPLEX

    faceCascade = cv2.CascadeClassifier('Cascades/haarcascade_frontalface_default.xml')
    while True:
        global isImagesUpdated
        img = camera.get_Image()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        image = copy.copy(img)
        faces = faceCascade.detectMultiScale(gray, 1.3, 5)
        cv2.putText(img, "'F4': Capture Image: ", (10, 340), font, 0.7, (0, 0, 255), 2, cv2.LINE_AA)

        for (x, y, w, h) in faces:
            # Press 'F4' to Capture Image for Customer dataset
            if keyboard.is_pressed('F4'):
                if faces is not None:
                    cwd = os.getcwd()
                    dir = os.path.join(cwd, "dataset", str(selectedCustomerId))
                    if os.path.exists(dir):
                        cv2.imwrite("dataset/" + str(selectedCustomerId) + "/" + str(selectedCustomerId) + ".jpg", image)
                        isImagesUpdated = True

            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if isImagesUpdated:
            cv2.putText(img, 'Succeeded! Customer Image Updated...', (80, 60), font, 0.8, (255, 0, 0), 2, cv2.LINE_AA)

        ret, jpg = cv2.imencode('.jpg', img)
        frame = jpg.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')


@app.route('/video_feed', methods=['GET', 'POST'])
def video_feed():
    im = capture_image(VideoCamera())
    return Response(im, mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video_feed2', methods=['GET', 'POST'])
def video_feed2():
    im = capture_image2(VideoCamera())
    return Response(im, mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/live_streaming')
def live_streaming():
    def get_live_streaming():
        encoder_model = 'model/facenet_keras.h5'
        encodings_path = 'encodings/encodings.pkl'

        face_detector = mtcnn.MTCNN()
        face_encoder = load_model(encoder_model, compile=False)
        encoding_dict = load_pickle(encodings_path)

        id = c_id = 0
        isCustomerIdentified = False
        c_fname = c_lname = c_address = c_phone = ""

        result = tbl_custmers.query.all()

        vc = cv2.VideoCapture(0)
        vc.set(3, 480)
        vc.set(4, 340)
        while vc.isOpened():
            ret, img = vc.read()
            # img = cv2.flip(img, 1)
            if not ret:
                break

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            results = face_detector.detect_faces(img_rgb)
            for res in results:
                if res['confidence'] < 0.99:
                    continue
                face, pt_1, pt_2 = get_face(img_rgb, res['box'])
                encode = get_encode(face_encoder, face, (160, 160))
                encode = l2_normalizer.transform(encode.reshape(1, -1))[0]
                id = 'unknown'

                distance = float("inf")
                for customer_id, db_encode in encoding_dict.items():
                    dist = cosine(db_encode, encode)
                    if dist < 0.5 and dist < distance:
                        id = customer_id
                        distance = dist

                if id == 'unknown':
                    try:
                        os.remove("templates/customer.txt")
                    except:
                        pass

                    cv2.rectangle(img, pt_1, pt_2, (0, 0, 255), 2)
                    cv2.putText(img, "Unknown", pt_1, cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 1)
                else:
                    for r in result:
                        if int(id) == r.customer_id:
                            c_id = r.customer_id
                            c_fname = r.customer_name.split(' ')[0]
                            c_lname = r.customer_name.split(' ')[1]
                            c_address = r.customer_address
                            c_phone = r.customer_phoneNo

                            try:
                                f = open("templates/customer.txt", "w")
                                f.write(str(c_id) + ',' + c_fname + ',' + c_lname + ',' + c_address + ',' + c_phone)
                                f.close()
                            except:
                                pass

                            isCustomerIdentified = True

                    cv2.rectangle(img, pt_1, pt_2, (0, 255, 0), 2)

                    cv2.putText(img, c_fname+f'-{100 - (distance * 100):.2f}%', (pt_1[0], pt_1[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                (0, 200, 200), 2)

                    # cv2.putText(img, f'-{100 - (distance * 100):.2f}%', (pt_1[0], pt_1[1] + 135),
                    #             cv2.FONT_HERSHEY_SIMPLEX, 1,
                    #             (0, 200, 200), 2)

            ret, jpeg = cv2.imencode('.jpg', img)
            frame = jpeg.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

            if isCustomerIdentified:
                break


    im = get_live_streaming()
    return Response(im, mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/get_file')
def get_file():
    try:
        f = open("templates/customer.txt", "r")
    except:
        abort(404)

    return f.read()

app.run(debug=True)
