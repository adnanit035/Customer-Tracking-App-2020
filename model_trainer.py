import os
import pickle
import numpy as np
import cv2
import mtcnn
from keras.models import load_model
from utils import get_face, l2_normalizer, normalize


def train_model():
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    encoder_model = 'model/facenet_keras.h5'
    customer_dir = 'dataset'
    encodings_path = 'encodings/encodings.pkl'

    # using MTCNN model to detect faces from images.
    face_detector = mtcnn.MTCNN()

    # loading encoded dataset images of known customers
    face_encoder = load_model(encoder_model)

    encoding_dict = dict()

    for customer_name in os.listdir(customer_dir):
        customer_directory = os.path.join(customer_dir, customer_name)
        encodes = []
        for img_name in os.listdir(customer_directory):
            img_path = os.path.join(customer_directory, img_name)
            img = cv2.imread(img_path)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            # detect faces from dataset images
            results = face_detector.detect_faces(img_rgb)
            # check if image contain face or not
            if results:
                # if image contain face then crop the face from image
                res = max(results, key=lambda b: b['box'][2] * b['box'][3])
                face, _, _ = get_face(img_rgb, res['box'])

                face = normalize(face)
                face = cv2.resize(face, (160, 160))
                encode = face_encoder.predict(np.expand_dims(face, axis=0))[0]
                encodes.append(encode)
        if encodes:
            encode = np.sum(encodes, axis=0)
            encode = l2_normalizer.transform(np.expand_dims(encode, axis=0))[0]
            encoding_dict[customer_name] = encode

    with open(encodings_path, 'bw') as file:
        pickle.dump(encoding_dict, file)

    return True
