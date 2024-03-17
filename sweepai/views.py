from flask import render_template, url_for, redirect, flash, request
from .models import Admin, Employee
from flask_login import login_user
from .forms import LoginForm, EmployeeForm
from . import db
from .forms import LoginForm, EmployeeForm
from . import db

def login():
    form = LoginForm()
    if form.validate_on_submit():
        # handle login
        admin = Admin.query.filter_by(email=form.email.data).first()
        if admin and admin.check_password(form.password.data):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid email or password')
    return render_template('login.html', form=form)

def create_employee():
    # handle employee creation
    form = EmployeeForm()
    if form.validate_on_submit():
        employee = Employee(name=form.name.data, email=form.email.data, position=form.position.data)
        db.session.add(employee)
        db.session.commit()
        flash('Employee created successfully')
        return redirect(url_for('display_employee'))
    return render_template('create_employee.html', form=form)

def display_employee():
    # handle employee display
    employees = Employee.query.all()
    return render_template('display_employee.html', employees=employees)

def edit_employee(id):
    # handle employee editing
    employee = Employee.query.get_or_404(id)
    form = EmployeeForm(obj=employee)
    if form.validate_on_submit():
        form.populate_obj(employee)
        db.session.commit()
        flash('Employee updated successfully')
        return redirect(url_for('display_employee'))
    return render_template('edit_employee.html', form=form)

def delete_employee(id):
    # handle employee deletion
    employee = Employee.query.get_or_404(id)
    db.session.delete(employee)
    db.session.commit()
    flash('Employee deleted successfully')
    return redirect(url_for('display_employee'))

