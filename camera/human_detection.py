import cv2

def detect_and_draw_person(image_path):
    """
    Detect if there is a person in the image using YOLOv4-tiny and draw rectangles around them.

    Parameters:
        image_path (str): Path to the image file to process.

    Returns:
        bool: True if a person is detected, False otherwise.
    """
    # Paths to YOLOv4-tiny files
    config_path = "yolo/yolov4-tiny.cfg"
    weights_path = "yolo/yolov4-tiny.weights"

    # Load YOLO model
    net = cv2.dnn.readNetFromDarknet(config_path, weights_path)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    # Get layer names and output layers
    layer_names = net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

    # Load the image
    image = cv2.imread(image_path)
    if image is None:
        print("Image not found or invalid.")
        return False

    (h, w) = image.shape[:2]

    # Prepare the image for YOLO
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (416, 416), swapRB=True, crop=False)
    net.setInput(blob)

    # Perform the detection
    detections = net.forward(output_layers)

    person_detected = False

    # Process detections
    for output in detections:
        for detection in output:
            scores = detection[5:]
            class_id = int(scores.argmax())
            confidence = scores[class_id]

            # Class ID 0 corresponds to "person" in COCO dataset
            if confidence > 0.5 and class_id == 0:
                person_detected = True
                box = detection[0:4] * [w, h, w, h]
                (centerX, centerY, width, height) = box.astype("int")

                # Calculate the box coordinates
                startX = int(centerX - (width / 2))
                startY = int(centerY - (height / 2))
                endX = int(centerX + (width / 2))
                endY = int(centerY + (height / 2))

                # Draw the box
                cv2.rectangle(image, (startX, startY), (endX, endY), (0, 255, 0), 1)

    # Save the output image
    cv2.imwrite(image_path, image)

    if person_detected:
        print("Person detected in the image.")
    else:
        print("No person detected in the image.")
    return person_detected
