CREATE TABLE bank_account_mapping (
    bank_account_id text PRIMARY KEY,
    erp_company text NOT NULL,
    erp_gl_account text NOT NULL,
    currency char(3) NOT NULL
);

INSERT INTO bank_account_mapping
    (bank_account_id, erp_company, erp_gl_account, currency)
VALUES
    ('BANK-INR-001', 'Demo Finance', 'Operating Bank - DF', 'INR');
