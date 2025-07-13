# app.py
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import uuid
from datetime import datetime

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///"+os.path.join(basedir,"FlashFund.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- Define the Admin User ID (FIXED) ---
ADMIN_USER_ID = "a1b2c3d4-e5f6-7890-1234-567890abcdef" 

# --- Database Model Class ---
class Donation(db.Model):
    """
    SQLAlchemy model for the 'donations' table, handling all states.
    """
    id = db.Column(db.Integer, primary_key=True)
    donorId = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Text, nullable=False) 
    status = db.Column(db.Text, default='pending', nullable=False) # 'pending', 'valid', or 'rejected'
    attestedBy = db.Column(db.Text, nullable=True) # ID of the validator who attested/rejected it
    validatorMessage = db.Column(db.Text, nullable=True) # Message from validator 

    def __repr__(self):
        return f'<Donation {self.id} by {self.donorId} - ${self.amount} ({self.status})>'

# --- Database Initialization ---
def init_db():
    """
    Initializes the database by creating all defined tables.
    This should be called once when the application starts.
    """
    with app.app_context():
        inspector = db.inspect(db.engine)
        if not inspector.has_table("donations"):
            db.create_all() # Creates tables based on the defined models
            print(f"SQLAlchemy database '{app.config['SQLALCHEMY_DATABASE_URI']}' created and 'donations' table initialized.")
            print(f"\n--- IMPORTANT ---")
            print(f"Your FIXED Admin User ID for validation is: {ADMIN_USER_ID}")
            print(f"Use this ID on the /validate page to approve/reject donations.")
            print(f"--- IMPORTANT ---\n")
        else:
            print(f"Database '{app.config['SQLALCHEMY_DATABASE_URI']}' and 'donations' table already exist.")
            print(f"\n--- IMPORTANT ---")
            print(f"Your FIXED Admin User ID for validation is: {ADMIN_USER_ID}")
            print(f"Use this ID on the /validate page to approve/reject donations.")
            print(f"--- IMPORTANT ---\n")


# --- Helper function for generating a user ID ---
def get_user_id():
    """
    Generates a unique user ID.
    Prioritizes MetaMask ID from form submission if available, otherwise generates a UUID.
    """
    # Check for MetaMask ID passed from the frontend form submission
    meta_mask_id = request.form.get('metaMaskUserId')
    if meta_mask_id and meta_mask_id != 'null' and meta_mask_id != 'undefined' and meta_mask_id != '':
        return meta_mask_id
    
    # If not a POST request, or MetaMask ID not provided/valid, generate new UUID
    return str(uuid.uuid4())

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def home():
    user_id = get_user_id() # This will be UUID on GET, or MetaMask ID on POST if connected
    message = None
    message_type = None

    if request.method == 'POST':
        # Check if it's a new donation submission
        if 'submit_donation' in request.form:
            amount_str = request.form.get('amount')
            description = request.form.get('description')
            current_timestamp = datetime.now().isoformat()

            # The donorId for the donation will be the user_id determined by get_user_id()
            actual_donor_id = user_id 

            try:
                # --- Donation Input Validators Checking ---
                if not amount_str:
                    raise ValueError("Donation amount cannot be empty.")

                try:
                    amount = float(amount_str)
                except ValueError:
                    raise ValueError("Donation amount must be a valid number.")

                if amount <= 0:
                    raise ValueError("Donation amount must be positive.")

                if not description or description.strip() == "":
                    raise ValueError("Description cannot be empty.")
                # --- End Donation Input Validators Checking ---

                # Create a new Donation object with 'pending' status
                new_donation = Donation(
                    donorId=actual_donor_id, # Use the determined donor ID
                    amount=amount,
                    description=description,
                    timestamp=current_timestamp,
                    status='pending' # Initial status is pending
                )
                db.session.add(new_donation)
                db.session.commit()

                message = "Donation submitted for attestation! It will appear in the public ledger once validated."
                message_type = "success"

            except ValueError as e:
                db.session.rollback()
                message = f"Validation Error: {e}"
                message_type = "error"
            except Exception as e:
                db.session.rollback()
                message = f"Failed to record donation: {e}"
                message_type = "error"
            
            # After POST, whether success or error, re-render the page with updated data
            # The user_id passed to render_template will be the one from the POST (could be MetaMask or UUID)

    # Fetch donations for rendering the page
    valid_donations = []
    rejected_donations = []
    donor_notifications = [] # New list for donor-specific messages

    try:
        # Fetch valid donations for the main ledger
        valid_donations = Donation.query.filter_by(status='valid').order_by(Donation.timestamp.desc()).limit(50).all()
        valid_donations = [{
            'id': d.id,
            'donorId': d.donorId,
            'amount': d.amount,
            'description': d.description,
            'timestamp': d.timestamp,
            'attestedBy': d.attestedBy,
            'validatorMessage': d.validatorMessage
        } for d in valid_donations]

        # Fetch rejected donations
        rejected_donations = Donation.query.filter_by(status='rejected').order_by(Donation.timestamp.desc()).limit(50).all()
        rejected_donations = [{
            'id': d.id,
            'donorId': d.donorId,
            'amount': d.amount,
            'description': d.description,
            'timestamp': d.timestamp,
            'attestedBy': d.attestedBy,
            'validatorMessage': d.validatorMessage
        } for d in rejected_donations]

        # Fetch notifications for the current donor (using the potentially MetaMask-derived user_id)
        processed_donations_by_user = Donation.query.filter_by(donorId=user_id).filter(Donation.status.in_(['valid', 'rejected'])).order_by(Donation.timestamp.desc()).all()

        for d in processed_donations_by_user:
            if d.status == 'valid':
                donor_notifications.append({
                    'type': 'success',
                    'text': f"Your donation of ${d.amount:.2f} for '{d.description}' has been APPROVED by {d.attestedBy}!"
                })
            elif d.status == 'rejected':
                reason = f" (Reason: {d.validatorMessage})" if d.validatorMessage else ""
                donor_notifications.append({
                    'type': 'error',
                    'text': f"Your donation of ${d.amount:.2f} for '{d.description}' has been REJECTED by {d.attestedBy}.{reason}"
                })

    except Exception as e:
        message = f"Error fetching donations or notifications: {e}"
        message_type = "error"

    return render_template('index.html',
                           user_id=user_id, # This user_id will be the current UUID or MetaMask ID from POST
                           valid_donations=valid_donations,
                           rejected_donations=rejected_donations,
                           donor_notifications=donor_notifications,
                           message=message,
                           message_type=message_type)

@app.route('/validate', methods=['GET', 'POST'])
def validate():
    current_browser_user_id = get_user_id() # This will be UUID on GET, or MetaMask ID on POST if connected
    message = None
    message_type = None
    is_admin_verified = False # Flag to control button visibility

    # For POST requests, process the admin ID verification or validation action
    if request.method == 'POST':
        entered_admin_id = request.form.get('admin_id_input', '').strip()
        
        if entered_admin_id == ADMIN_USER_ID:
            is_admin_verified = True # Admin ID is correct
            
            # Now check if it's an approve/reject action
            if 'action' in request.form and request.form['action'] in ['approve', 'reject']:
                donation_id = request.form.get('donation_id', type=int)
                action = request.form.get('action') # 'approve' or 'reject'
                validator_note = request.form.get('note', '').strip() # Note from validator

                if donation_id is None:
                    message = "Invalid donation ID for attestation."
                    message_type = "error"
                else:
                    try:
                        donation_record = Donation.query.get(donation_id)
                        if donation_record and donation_record.status == 'pending':
                            donation_record.attestedBy = entered_admin_id # Use the entered admin ID
                            donation_record.validatorMessage = validator_note

                            if action == 'approve':
                                donation_record.status = 'valid'
                                message = f"Donation ID {donation_id} successfully validated by Admin!"
                                message_type = "success"
                            elif action == 'reject':
                                donation_record.status = 'rejected'
                                message = f"Donation ID {donation_id} rejected by Admin."
                                message_type = "error"

                            db.session.commit()
                        elif donation_record and donation_record.status != 'pending':
                            message = f"Donation ID {donation_record.id} has already been processed ({donation_record.status})."
                            message_type = "info"
                        else:
                            message = f"Donation ID {donation_id} not found."
                            message_type = "error"

                    except Exception as e:
                        db.session.rollback()
                        message = f"Error processing attestation: {e}"
                        message_type = "error"
            else: # This is the initial 'verify_admin' action
                message = "Admin ID verified. You can now approve/reject donations."
                message_type = "success"
        else:
            message = "Access Denied: Incorrect Admin ID."
            message_type = "error"
            # is_admin_verified remains False

        # After POST, whether success or error, re-render the page with updated data
        # The last_admin_id is passed to pre-fill the input box
        # The current_browser_user_id is passed for display
        return render_template('validate.html',
                               pending_donations=Donation.query.filter_by(status='pending').order_by(Donation.timestamp.asc()).all(),
                               message=message,
                               message_type=message_type,
                               is_admin_verified=is_admin_verified,
                               last_admin_id=entered_admin_id,
                               user_id=current_browser_user_id) # Pass the current browser user ID (could be MetaMask if submitted)


    # For GET requests, fetch pending donations
    pending_donations = []
    try:
        pending_donations = Donation.query.filter_by(status='pending').order_by(Donation.timestamp.asc()).all()
        pending_donations = [{
            'id': d.id,
            'donorId': d.donorId,
            'amount': d.amount,
            'description': d.description,
            'timestamp': d.timestamp
        } for d in pending_donations]
    except Exception as e:
        message = f"Error fetching pending donations: {e}"
        message_type = "error"

    # For GET, the last_admin_id is not persisted by default, so it will be empty
    last_admin_id = request.args.get('last_admin_id', '')
    if last_admin_id == ADMIN_USER_ID: # If the last entered ID was correct, keep buttons enabled
        is_admin_verified = True

    return render_template('validate.html',
                           pending_donations=pending_donations,
                           message=message,
                           message_type=message_type,
                           is_admin_verified=is_admin_verified, # Pass the flag to the template
                           last_admin_id=last_admin_id, # Pass the last entered ID
                           user_id=current_browser_user_id) # Pass the current browser user ID (UUID on GET)


@app.route('/blockchain_concepts')
def blockchain_concepts():
    """Renders the page explaining blockchain concepts."""
    # Get a user ID for display on this page too, if needed
    user_id = get_user_id() # Will be UUID on GET
    return render_template('blockchain_concepts.html', user_id=user_id)

if __name__ == '__main__':
    # Initialize the database when the application starts
    init_db()
    app.run(debug=True)
