-- Create the manufactured schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS manufactured;

-- Create the keeco table with proper columns
CREATE TABLE IF NOT EXISTS manufactured.keeco (
	id SERIAL PRIMARY KEY,
	category VARCHAR(100),
	parent_name VARCHAR(255),
	sku VARCHAR(100) UNIQUE NOT NULL,
	type_size VARCHAR(100),
	price_per_unit DECIMAL(10,2),
	units_per_case INTEGER,
	specs JSONB,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on SKU for faster lookups
CREATE INDEX IF NOT EXISTS idx_keeco_sku ON manufactured.keeco(sku);

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
	NEW.updated_at = CURRENT_TIMESTAMP;
	RETURN NEW;
END;
$$ language 'plpgsql';

-- Create a trigger to automatically update the updated_at column
DROP TRIGGER IF EXISTS update_keeco_updated_at ON manufactured.keeco;
CREATE TRIGGER update_keeco_updated_at
	BEFORE UPDATE ON manufactured.keeco
	FOR EACH ROW
	EXECUTE FUNCTION update_updated_at_column();