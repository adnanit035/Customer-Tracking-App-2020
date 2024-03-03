import cv2


class VideoCamera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        self.video.set(3, 480)  # set Width
        self.video.set(4, 340)  # set Height

    def __del__(self):
        self.video.release()

    def get_Image(self):
        ret, img = self.video.read()
        img = cv2.flip(img, 1)

        return img
