from sweepai.core.chat import ChatGPT

class HotelChatbot(ChatGPT):
    def book_room(self, room_type: str, check_in_date: str, check_out_date: str):
        # Logic for booking a room
        # This is just a placeholder and the actual implementation may vary
        print("Booking room")

    def check_availability(self, room_type: str, check_in_date: str, check_out_date: str):
        # Logic for checking room availability
        # This is just a placeholder and the actual implementation may vary
        print("Checking availability")

    def answer_query(self, query: str):
        # Logic for answering a query
        # This is just a placeholder and the actual implementation may vary
        print("Answering query")