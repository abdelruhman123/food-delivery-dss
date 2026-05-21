-- =============================================================================
-- Food Delivery DSS – Sample Seed Data
-- Run AFTER db_schema.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- kitchen_staffing  –  active chef headcount
-- -----------------------------------------------------------------------------
INSERT INTO kitchen_staffing (station_name, chef_count) VALUES
    ('grill',    2),
    ('fryer',    1),
    ('assembly', 2),
    ('drinks',   1),
    ('saute',    2),
    ('pastry',   1),
    ('plating',  2),
    ('salad',    1),
    ('espresso', 2),
    ('cold_bar', 1),
    ('bakery',   1)
ON CONFLICT (station_name) DO UPDATE
    SET chef_count = EXCLUDED.chef_count,
        updated_at = NOW();


-- -----------------------------------------------------------------------------
-- live_orders  –  3 active orders (6 item lines) for workload testing
-- -----------------------------------------------------------------------------
INSERT INTO live_orders
    (order_id, item_name, station_name, quantity, prep_time_assigned, remaining_time, status)
VALUES
    -- Order A: burger meal
    ('ORD-001', 'Burger',    'grill',    2, 16.00, 12.00, 'Cooking'),
    ('ORD-001', 'Fries',     'fryer',    1,  5.00,  5.00, 'Pending'),
    ('ORD-001', 'Soft Drink','drinks',   2,  1.00,  1.00, 'Pending'),

    -- Order B: fine-dining table
    ('ORD-002', 'Steak',     'grill',    1, 20.00, 18.00, 'Cooking'),
    ('ORD-002', 'Pasta',     'saute',    2, 15.00, 10.00, 'Cooking'),

    -- Order C: cafe order
    ('ORD-003', 'Latte',     'espresso', 2,  4.00,  3.00, 'Cooking'),
    ('ORD-003', 'Croissant', 'bakery',   3,  3.00,  3.00, 'Pending');
