-- ============================================================================
-- Migration: Create zones table for area_density mapping
-- Purpose: Map Egyptian districts to area density categories
-- Author: Food Delivery DSS Team
-- Date: 2024
-- ============================================================================

-- Drop existing table if exists (for clean rebuild)
DROP TABLE IF EXISTS zones CASCADE;

-- Create zones table
CREATE TABLE zones (
    zone_id         SERIAL PRIMARY KEY,
    district_name   VARCHAR(100) NOT NULL,
    latitude        DECIMAL(10, 7) NOT NULL,
    longitude       DECIMAL(10, 7) NOT NULL,
    area_density    VARCHAR(20) NOT NULL CHECK (area_density IN ('residential', 'commercial', 'mixed')),
    city            VARCHAR(50) DEFAULT 'Cairo',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for fast spatial lookups
CREATE INDEX idx_zones_lat_lng ON zones(latitude, longitude);
CREATE INDEX idx_zones_area_density ON zones(area_density);

-- Insert Egyptian districts with predefined area densities
INSERT INTO zones (district_name, latitude, longitude, area_density, city) VALUES
    -- Cairo - Residential Areas
    ('Maadi', 29.9602, 31.2501, 'residential', 'Cairo'),
    ('Heliopolis', 30.0908, 31.3219, 'residential', 'Cairo'),
    ('Nasr City', 30.0444, 31.3486, 'residential', 'Cairo'),
    ('New Cairo', 30.0330, 31.4913, 'residential', 'Cairo'),
    ('6th of October City', 29.9520, 30.9380, 'residential', 'Giza'),
    ('Sheikh Zayed', 30.0200, 30.9700, 'residential', 'Giza'),
    ('Zamalek', 30.0626, 31.2197, 'residential', 'Cairo'),
    ('Garden City', 30.0444, 31.2357, 'residential', 'Cairo'),
    ('Dokki', 30.0380, 31.2120, 'residential', 'Giza'),
    ('Mohandessin', 30.0626, 31.2000, 'residential', 'Giza'),
    
    -- Cairo - Commercial Areas
    ('Downtown Cairo', 30.0444, 31.2357, 'commercial', 'Cairo'),
    ('Tahrir Square', 30.0444, 31.2336, 'commercial', 'Cairo'),
    ('Ramses', 30.0626, 31.2456, 'commercial', 'Cairo'),
    ('Ataba', 30.0520, 31.2490, 'commercial', 'Cairo'),
    ('Abbasiya', 30.0730, 31.2830, 'commercial', 'Cairo'),
    ('Shubra', 30.1090, 31.2440, 'commercial', 'Cairo'),
    ('City Stars Mall Area', 30.0730, 31.3440, 'commercial', 'Cairo'),
    ('Mall of Arabia Area', 30.0100, 30.9700, 'commercial', 'Giza'),
    
    -- Cairo - Mixed Areas
    ('Giza Square', 30.0131, 31.2089, 'mixed', 'Giza'),
    ('Faisal', 30.0170, 31.1040, 'mixed', 'Giza'),
    ('Haram', 29.9870, 31.1480, 'mixed', 'Giza'),
    ('Imbaba', 30.0760, 31.2070, 'mixed', 'Giza'),
    ('Agouza', 30.0560, 31.2010, 'mixed', 'Giza'),
    ('Hadayek El Kobba', 30.0810, 31.2880, 'mixed', 'Cairo'),
    ('Ain Shams', 30.1310, 31.3190, 'mixed', 'Cairo'),
    ('Matariya', 30.1210, 31.3080, 'mixed', 'Cairo'),
    ('Zeitoun', 30.0960, 31.3140, 'mixed', 'Cairo'),
    ('Manial', 30.0260, 31.2290, 'mixed', 'Cairo'),
    
    -- Alexandria - Major Areas
    ('Alexandria Downtown', 31.2001, 29.9187, 'commercial', 'Alexandria'),
    ('Smouha', 31.2156, 29.9467, 'residential', 'Alexandria'),
    ('Miami', 31.2890, 30.0050, 'residential', 'Alexandria'),
    ('Sidi Gaber', 31.2440, 29.9700, 'mixed', 'Alexandria');

-- Add comment
COMMENT ON TABLE zones IS 'Predefined zones for Egyptian districts with area density classification. Used for area_density feature in ML model.';

-- Create helper function to find nearest zone with safety check
CREATE OR REPLACE FUNCTION get_nearest_zone(
    p_latitude DECIMAL(10, 7),
    p_longitude DECIMAL(10, 7)
) RETURNS TABLE (
    zone_id INT,
    district_name VARCHAR(100),
    area_density VARCHAR(20),
    distance_km DECIMAL(10, 4)
) AS $$
DECLARE
    nearest_distance DECIMAL(10, 4);
BEGIN
    -- Find the nearest zone distance first
    SELECT 
        ROUND(
            (6371 * acos(
                cos(radians(p_latitude)) * 
                cos(radians(z.latitude)) * 
                cos(radians(z.longitude) - radians(p_longitude)) + 
                sin(radians(p_latitude)) * 
                sin(radians(z.latitude))
            ))::NUMERIC, 
            4
        )
    INTO nearest_distance
    FROM zones z
    ORDER BY 
        (6371 * acos(
            cos(radians(p_latitude)) * 
            cos(radians(z.latitude)) * 
            cos(radians(z.longitude) - radians(p_longitude)) + 
            sin(radians(p_latitude)) * 
            sin(radians(z.latitude))
        ))
    LIMIT 1;
    
    -- If nearest zone is > 5km away, return 'unknown' instead of forcing assignment
    IF nearest_distance > 5.0 THEN
        RETURN QUERY
        SELECT 
            NULL::INT as zone_id,
            'Unknown'::VARCHAR(100) as district_name,
            'unknown'::VARCHAR(20) as area_density,
            nearest_distance as distance_km;
    ELSE
        -- Return the actual nearest zone
        RETURN QUERY
        SELECT 
            z.zone_id,
            z.district_name,
            z.area_density,
            ROUND(
                (6371 * acos(
                    cos(radians(p_latitude)) * 
                    cos(radians(z.latitude)) * 
                    cos(radians(z.longitude) - radians(p_longitude)) + 
                    sin(radians(p_latitude)) * 
                    sin(radians(z.latitude))
                ))::NUMERIC, 
                4
            ) AS distance_km
        FROM zones z
        ORDER BY distance_km ASC
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Test the function
SELECT * FROM get_nearest_zone(30.0444, 31.2357);

COMMENT ON FUNCTION get_nearest_zone IS 'Returns the nearest zone for given coordinates using Haversine distance formula. Returns area_density=unknown if nearest zone is >5km away.';
