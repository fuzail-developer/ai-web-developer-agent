from datetime import datetime
from functools import wraps
import os

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import DecimalField, IntegerField, PasswordField, SelectField, StringField, SubmitField, TextAreaField, ValidationError
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'dev-secret-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL') or 'sqlite:///crm_saas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), nullable=False, default='user')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship('Tenant', backref='users')


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='lead')
    purchase_year = db.Column(db.Integer, nullable=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship('Tenant', backref='customers')


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tenant = db.relationship('Tenant', backref='documents')


class SignupForm(FlaskForm):
    company_name = StringField('Company Name', validators=[DataRequired(), Length(min=2, max=160)])
    full_name = StringField('Name', validators=[DataRequired(), Length(min=2, max=160)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=128)])
    role = SelectField(
        'Role',
        choices=[('admin', 'Admin'), ('sales', 'Sales'), ('manager', 'Manager'), ('user', 'User')],
        validators=[DataRequired()],
        default='admin',
    )
    submit = SubmitField('Create Account')

    def validate_company_name(self, company_name):
        existing = Tenant.query.filter(func.lower(Tenant.name) == company_name.data.strip().lower()).first()
        if existing:
            raise ValidationError('Company already exists. Use another name.')

    def validate_email(self, email):
        existing = User.query.filter(func.lower(User.email) == email.data.strip().lower()).first()
        if existing:
            raise ValidationError('Email already registered. Please login.')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class CustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField('Email', validators=[Optional(), Email()])
    phone = StringField('Phone', validators=[Optional(), Length(max=40)])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    status = SelectField('Status', choices=[('lead', 'Lead'), ('customer', 'Customer')], validators=[DataRequired()])
    purchase_year = IntegerField('Purchase Year', validators=[Optional(), NumberRange(min=2000, max=2100)])
    amount = DecimalField('Amount (INR)', validators=[Optional(), NumberRange(min=0)], places=2, default=0)
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=4000)])
    submit = SubmitField('Save Customer')


class DocumentForm(FlaskForm):
    title = StringField('Document Title', validators=[DataRequired(), Length(min=2, max=200)])
    content = TextAreaField('Document Content', validators=[DataRequired(), Length(min=20, max=20000)])
    submit = SubmitField('Upload to Knowledge Base')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if current_user.role not in allowed_roles:
                flash('You do not have access to this section.', 'danger')
                return redirect(url_for('dashboard'))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = SignupForm()
    if form.validate_on_submit():
        tenant = Tenant(name=form.company_name.data.strip())
        db.session.add(tenant)
        db.session.flush()

        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            password_hash=generate_password_hash(form.password.data, method='pbkdf2:sha256'),
            role=form.role.data,
            tenant_id=tenant.id,
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Account not found. Please create account first.', 'warning')
            return redirect(url_for('signup'))

        if check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=True)
            flash('Login successful.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('login.html', form=form, quick_login_enabled=False)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    tenant_id = current_user.tenant_id
    total_customers = Customer.query.filter_by(tenant_id=tenant_id).count()
    total_leads = Customer.query.filter_by(tenant_id=tenant_id, status='lead').count()
    revenue = (
        db.session.query(func.coalesce(func.sum(Customer.amount), 0.0))
        .filter_by(tenant_id=tenant_id, status='customer')
        .scalar()
    )
    recent_customers = (
        Customer.query.filter_by(tenant_id=tenant_id).order_by(Customer.created_at.desc()).limit(6).all()
    )

    return render_template(
        'dashboard.html',
        total_customers=total_customers,
        total_leads=total_leads,
        revenue=revenue,
        recent_customers=recent_customers,
    )


@app.route('/customers')
@login_required
def customers():
    q_city = (request.args.get('city') or '').strip()
    q_year = (request.args.get('year') or '').strip()

    query = Customer.query.filter_by(tenant_id=current_user.tenant_id)
    if q_city:
        query = query.filter(Customer.city.ilike(f'%{q_city}%'))
    if q_year.isdigit():
        query = query.filter(Customer.purchase_year == int(q_year))

    rows = query.order_by(Customer.created_at.desc()).all()
    return render_template('customers.html', rows=rows, q_city=q_city, q_year=q_year)


@app.route('/customers/new', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'sales', 'manager')
def customer_new():
    form = CustomerForm()
    if form.validate_on_submit():
        record = Customer(
            tenant_id=current_user.tenant_id,
            name=form.name.data.strip(),
            email=(form.email.data or '').strip() or None,
            phone=(form.phone.data or '').strip() or None,
            city=(form.city.data or '').strip() or None,
            status=form.status.data,
            purchase_year=form.purchase_year.data,
            amount=float(form.amount.data or 0),
            notes=(form.notes.data or '').strip() or None,
        )
        db.session.add(record)
        db.session.commit()
        flash('Customer saved.', 'success')
        return redirect(url_for('customers'))

    return render_template('customer_form.html', form=form)


@app.route('/analytics')
@login_required
@role_required('admin', 'manager')
def analytics():
    tenant_id = current_user.tenant_id

    monthly = (
        db.session.query(
            func.strftime('%Y-%m', Customer.created_at).label('month'),
            func.coalesce(func.sum(Customer.amount), 0.0).label('revenue'),
        )
        .filter(Customer.tenant_id == tenant_id, Customer.status == 'customer')
        .group_by('month')
        .order_by('month')
        .all()
    )

    labels = [m.month for m in monthly]
    values = [float(m.revenue or 0) for m in monthly]

    return render_template('analytics.html', labels=labels, values=values)


@app.route('/rag', methods=['GET', 'POST'])
@login_required
def rag_search():
    form = DocumentForm()
    if form.validate_on_submit():
        doc = Document(
            tenant_id=current_user.tenant_id,
            title=form.title.data.strip(),
            content=form.content.data.strip(),
        )
        db.session.add(doc)
        db.session.commit()
        flash('Document uploaded to tenant knowledge base.', 'success')
        return redirect(url_for('rag_search'))

    query = (request.args.get('q') or '').strip()
    customer_hits = []
    document_hits = []

    if query:
        customer_hits = (
            Customer.query.filter(Customer.tenant_id == current_user.tenant_id)
            .filter(
                or_(
                    Customer.name.ilike(f'%{query}%'),
                    Customer.city.ilike(f'%{query}%'),
                    Customer.notes.ilike(f'%{query}%'),
                )
            )
            .order_by(Customer.created_at.desc())
            .limit(10)
            .all()
        )

        document_hits = (
            Document.query.filter(Document.tenant_id == current_user.tenant_id)
            .filter(or_(Document.title.ilike(f'%{query}%'), Document.content.ilike(f'%{query}%')))
            .order_by(Document.created_at.desc())
            .limit(10)
            .all()
        )

    return render_template(
        'rag.html',
        form=form,
        query=query,
        customer_hits=customer_hits,
        document_hits=document_hits,
    )


@app.route('/billing')
@login_required
@role_required('admin')
def billing():
    stripe_key = os.getenv('STRIPE_SECRET_KEY')
    configured = bool(stripe_key)
    return render_template('billing.html', stripe_configured=configured)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
