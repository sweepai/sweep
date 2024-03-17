from flask import Blueprint
from .views import login, create_employee, display_employee, edit_employee, delete_employee

main = Blueprint('main', __name__)

@main.route('/login', methods=['GET', 'POST'])
def login_view():
    return login()

@main.route('/create_employee', methods=['GET', 'POST'])
def create_employee_view():
    return create_employee()

@main.route('/display_employee')
def display_employee_view():
    return display_employee()

@main.route('/edit_employee/<int:id>', methods=['GET', 'POST'])
def edit_employee_view(id):
    return edit_employee(id)

@main.route('/delete_employee/<int:id>', methods=['POST'])
def delete_employee_view(id):
    return delete_employee(id)

