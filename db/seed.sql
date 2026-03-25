-- Sample seed data for demo and report screenshots.

-- Roles and permissions
INSERT INTO roles (role_name) VALUES
    ('public'), ('staff'), ('leader'), ('admin')
ON CONFLICT DO NOTHING;

INSERT INTO permissions (perm_code, perm_desc) VALUES
    ('view_policy', 'View policy documents'),
    ('upload_policy', 'Upload policy documents'),
    ('edit_indicator', 'Edit indicators'),
    ('approve_audit', 'Approve audit results'),
    ('manage_users', 'Manage users and roles')
ON CONFLICT DO NOTHING;

-- Users (passwords: admin123 / staff123 / leader123 / public123)
INSERT INTO app_users (username, password_hash, display_name, email, status) VALUES
    ('admin', 'pbkdf2_sha256$120000$Z3NxdG1wWHdRZ0VzVnJQTA$VHy7gCLuoaYxWQdWETOVWnHIW48H1rAnsDMc5QfO-PE', 'Admin', 'admin@example.com', 'active'),
    ('staff', 'pbkdf2_sha256$120000$Z3NxdG1wWHdRZ0VzVnJQTA$JgIPD8cbbk3XjsQKsZlE55Rv3v0JSkQGmkNWJhERepk', 'Staff', 'staff@example.com', 'active'),
    ('leader', 'pbkdf2_sha256$120000$Z3NxdG1wWHdRZ0VzVnJQTA$HfnxQV3ITxlSkLIhBFIh_R-4RDsLp0iEvikkzApb1dI', 'Leader', 'leader@example.com', 'active'),
    ('public', 'pbkdf2_sha256$120000$Z3NxdG1wWHdRZ0VzVnJQTA$UbglXhDNBhOanVh6qAHmxVm509UIA7T3BiaQYS_hkHY', 'Public', 'public@example.com', 'active')
ON CONFLICT DO NOTHING;

-- User roles
INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM app_users u
JOIN roles r ON r.role_name = 'admin'
WHERE u.username = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM app_users u
JOIN roles r ON r.role_name = 'staff'
WHERE u.username = 'staff'
ON CONFLICT DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM app_users u
JOIN roles r ON r.role_name = 'leader'
WHERE u.username = 'leader'
ON CONFLICT DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.user_id, r.role_id
FROM app_users u
JOIN roles r ON r.role_name = 'public'
WHERE u.username = 'public'
ON CONFLICT DO NOTHING;

-- Role permissions
INSERT INTO role_permissions (role_id, perm_code)
SELECT r.role_id, p.perm_code
FROM roles r
JOIN permissions p ON p.perm_code IN ('view_policy', 'upload_policy', 'edit_indicator', 'approve_audit', 'manage_users')
WHERE r.role_name = 'admin'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, perm_code)
SELECT r.role_id, p.perm_code
FROM roles r
JOIN permissions p ON p.perm_code IN ('view_policy', 'upload_policy', 'edit_indicator')
WHERE r.role_name = 'staff'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, perm_code)
SELECT r.role_id, p.perm_code
FROM roles r
JOIN permissions p ON p.perm_code IN ('view_policy', 'approve_audit')
WHERE r.role_name = 'leader'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, perm_code)
SELECT r.role_id, p.perm_code
FROM roles r
JOIN permissions p ON p.perm_code IN ('view_policy')
WHERE r.role_name = 'public'
ON CONFLICT DO NOTHING;
