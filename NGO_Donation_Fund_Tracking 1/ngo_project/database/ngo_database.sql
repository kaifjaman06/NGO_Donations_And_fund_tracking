-- Create the application database before defining its tables.
CREATE DATABASE IF NOT EXISTS ngo_fund_tracking;
USE ngo_fund_tracking;

-- Store staff accounts used by the Flask session-based login flow.
CREATE TABLE IF NOT EXISTS admin (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store donor identity and contact information.
CREATE TABLE IF NOT EXISTS donors (
    donor_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150),
    phone VARCHAR(20),
    address TEXT,
    donor_type ENUM('Individual', 'Corporate', 'Trust', 'Government', 'Other') DEFAULT 'Individual',
    pan_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Store projects and their fundraising targets.
CREATE TABLE IF NOT EXISTS projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    description TEXT,
    target_amount DECIMAL(14,2) DEFAULT 0.00,
    start_date DATE,
    end_date DATE,
    status ENUM('Planned', 'Active', 'Completed', 'On Hold', 'Cancelled') DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Link donations to donors and optionally to a project.
CREATE TABLE IF NOT EXISTS donations (
    donation_id INT AUTO_INCREMENT PRIMARY KEY,
    donor_id INT NOT NULL,
    project_id INT,
    amount DECIMAL(14,2) NOT NULL,
    payment_mode ENUM('Online', 'Cheque', 'Bank Transfer', 'Cash', 'UPI', 'Razorpay', 'Stripe', 'PayPal', 'Debit Card', 'Credit Card') NOT NULL,
    transaction_reference VARCHAR(100),
    donation_date DATE NOT NULL,
    receipt_no VARCHAR(30) UNIQUE,
    remarks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES donors(donor_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
);

-- Track project spending used by balance and report calculations.
CREATE TABLE IF NOT EXISTS expenses (
    expense_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    category VARCHAR(100) NOT NULL,
    amount DECIMAL(14,2) NOT NULL,
    expense_date DATE NOT NULL,
    description TEXT,
    approved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX idx_donations_donor ON donations(donor_id);
CREATE INDEX idx_donations_project ON donations(project_id);
CREATE INDEX idx_donations_date ON donations(donation_date);
CREATE INDEX idx_expenses_project ON expenses(project_id);
CREATE INDEX idx_expenses_date ON expenses(expense_date);

INSERT INTO projects (project_name, description, target_amount, start_date, status) VALUES
('Education for All', 'Providing school supplies and tuition support to underprivileged children', 500000.00, '2025-01-01', 'Active'),
('Clean Water Initiative', 'Installing water purification units in rural villages', 750000.00, '2025-02-01', 'Active'),
('Emergency Relief Fund', 'Disaster relief and emergency food/medical aid', 1000000.00, '2025-01-01', 'Active');

-- Sample donors
INSERT INTO donors (name, email, phone, donor_type) VALUES
('Ravi Kumar', 'ravi.kumar@example.com', '9876543210', 'Individual'),
('TechCorp Solutions Pvt Ltd', 'csr@techcorp.example.com', '9800011122', 'Corporate'),
('Anjali Trust', 'contact@anjalitrust.example.com', '9900033344', 'Trust');
