from flask import Flask, request, jsonify
from flask.helpers import send_file
import numpy as np
import onnxruntime

import cv2
import json

app = Flask(__name__,
            static_url_path='/', 
            static_folder='web')

ort_sessions = {
    "original": onnxruntime.InferenceSession("efficientnet-lite4-11.onnx"),
    "int8": onnxruntime.InferenceSession("efficientnet-lite4-11-int8.onnx"),
    "qdq": onnxruntime.InferenceSession("efficientnet-lite4-11-qdq.onnx")
}

# load the labels text file
labels = json.load(open("labels_map.txt", "r"))

# set image file dimensions to 224x224 by resizing and cropping image from center
def pre_process_edgetpu(img, dims):
    output_height, output_width, _ = dims
    img = resize_with_aspectratio(img, output_height, output_width, inter_pol=cv2.INTER_LINEAR)
    img = center_crop(img, output_height, output_width)
    img = np.asarray(img, dtype='float32')
    # converts jpg pixel value from [0 - 255] to float array [-1.0 - 1.0]
    img -= [127.0, 127.0, 127.0]
    img /= [128.0, 128.0, 128.0]
    return img

# resize the image with a proportional scale
def resize_with_aspectratio(img, out_height, out_width, scale=87.5, inter_pol=cv2.INTER_LINEAR):
    height, width, _ = img.shape
    new_height = int(100. * out_height / scale)
    new_width = int(100. * out_width / scale)
    if height > width:
        w = new_width
        h = int(new_height * height / width)
    else:
        h = new_height
        w = int(new_width * width / height)
    img = cv2.resize(img, (w, h), interpolation=inter_pol)
    return img

# crop the image around the center based on given height and width
def center_crop(img, out_height, out_width):
    height, width, _ = img.shape
    left = int((width - out_width) / 2)
    right = int((width + out_width) / 2)
    top = int((height - out_height) / 2)
    bottom = int((height + out_height) / 2)
    img = img[top:bottom, left:right]
    return img

@app.route("/")
def indexPage():
    # Haven't used the secure way to send files yet
    return send_file("web/index.html")    

@app.route("/analyze", methods=["POST"])
def analyze():
    content = request.files.get('0', '').read()
    model_choice = request.form.get("model", "original")

    if model_choice not in ort_sessions:
        return jsonify({"error": "Ungültiges Modell gewählt."}), 400

    session = ort_sessions[model_choice]

    img = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_UNCHANGED)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = pre_process_edgetpu(img, (224, 224, 3))
    img_batch = np.expand_dims(img, axis=0)

    try:
        results = session.run(["Softmax:0"], {"images:0": img_batch})[0]
    except:
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        results = session.run([output_name], {input_name: img_batch})[0]

    top_indices = reversed(results[0].argsort()[-5:])
    result_list = [{"class": labels[str(i)], "value": float(results[0][i])} for i in top_indices]

    return jsonify(result_list)    
