from pathlib import Path
R=Path(__file__).parent;D=R/'scene00-v2';D.mkdir(exist_ok=True)
source=(R/'scene00-audio.py').read_text(encoding='utf8')
old=source[source.index("text='"):source.index("\ndirection=")]
text='Khi học toán, có lời giải chưa chắc là đã hiểu bài. Học sinh dễ làm theo đáp án mà bỏ qua cách suy luận, còn giáo viên khó theo sát từng bước của cả lớp. Ngay cả AI cũng có thể lập luận sai. Math Mate hướng tới việc gợi mở và phản hồi theo từng bước, giúp học sinh tự tìm cách giải. Sau khi đăng nhập, cô Thu Hà quản lý lớp, học sinh, học liệu, lý thuyết và báo cáo trong cùng một không gian. Cô chọn phiếu luyện tập, đặt hạn nộp và giao những câu phù hợp cho lớp. Từ đây, thầy cô tiếp tục theo dõi tiến độ và xem lại bài làm của học sinh.'
source=source.replace("/'scene00'","/'scene00-v2'").replace(old,'text='+repr(text))
(R/'scene00-v2-audio.py').write_text(source,encoding='utf8')
capture=(R/'capture-scene00.cjs').read_text(encoding='utf8').replace("path.join(R,'scene00')","path.join(R,'scene00-v2')")
capture=capture.replace("record('classroom',10","record('classroom',19").replace("record('configure',11","record('configure',13")
capture=capture.replace('Đạo hàm — luyện tập tuần 12, hạn 15/11','Đạo hàm — luyện tập có hướng dẫn')
(R/'capture-scene00-v2.cjs').write_text(capture,encoding='utf8')
print('Standalone scene V2 scripts ready')
