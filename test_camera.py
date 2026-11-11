import cv2

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("카메라를 열 수 없습니다. 인덱스를 1, 2 등으로 바꿔 보세요.")
else:
    print("카메라 연결 성공. ESC를 누르면 종료합니다.")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow('Camera Test', frame)
        if cv2.waitKey(1) & 0xFF == 27:  # ESC
            break
    cap.release()
    cv2.destroyAllWindows()
