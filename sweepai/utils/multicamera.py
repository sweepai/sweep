import cv2
import multiprocessing

def capture_frames(camera_id, frame_queue):
    """
    Capture video from a camera and put the frames in a queue.

    Args:
        camera_id (int): The ID of the camera.
        frame_queue (multiprocessing.Queue): The queue to put the frames in.
    """
    cap = cv2.VideoCapture(camera_id)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_queue.put(frame)

    cap.release()

def main():
    """
    Create a separate process for each camera to capture video and put the frames in a queue.
    """
    cameras = [0, 1]  # List of camera IDs
    processes = []
    queues = []

    for camera_id in cameras:
        frame_queue = multiprocessing.Queue()
        queues.append(frame_queue)

        p = multiprocessing.Process(target=capture_frames, args=(camera_id, frame_queue))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

if __name__ == "__main__":
    main()