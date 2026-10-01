# ---------------------------------------------------------------------------
# Orders table
#
# order-api writes new rows (PutItem) with status=PENDING. Both workers
# only ever update the status/updated_at attributes of an existing row -
# neither one creates or deletes anything here. See app/db.py in each
# service for exactly which calls each one makes.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "orders" {
  name = "${var.project_name}-orders"

  # On-demand rather than provisioned: load-test traffic is deliberately
  # spiky (k6 ramps 10 -> 150 VUs), and this table sits idle between
  # sessions. Provisioned capacity would mean either paying for headroom
  # you don't use most of the time, or throttling during the ramp.
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "order_id"

  attribute {
    name = "order_id"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Inventory table
#
# inventory-worker is the only service that touches this table. Reservation
# and release both go through a ConditionExpression on quantity_available
# (see reserve_item/release_item in inventory-worker/app/db.py), which is
# why no separate lock or DynamoDB transaction is needed here - two pods
# racing on the same SKU is safe by construction.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "inventory" {
  name         = "${var.project_name}-inventory"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "sku"

  attribute {
    name = "sku"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Seed stock for the load test.
#
# These five SKUs match load-test/order-api-load.js exactly.
# quantity_available is set high enough that a full 13-minute run won't
# exhaust stock mid-run and start producing INVENTORY_FAILED instead of
# exercising the happy path. Math: an order has 1-3 of the 5 SKUs with
# quantity 1-3, so each SKU drains ~0.8 units per order. A full run creates
# ~120k orders (~96k units per SKU). The old seed of 5000 ran out after
# ~6k orders (~2 minutes in, Session 3). 500000 gives ~5x headroom, which
# also covers stock leaked by PAYMENT_FAILED orders (no compensation yet).
#
# IMPORTANT: terraform apply re-applies these values on every run, which
# will overwrite whatever quantity_available has drifted to after real
# testing. That's fine for this project's destroy/recreate-between-sessions
# workflow, but if you ever want seed data to persist independent of
# Terraform's state, remove these resources after the first apply and
# manage stock manually from then on.
# ---------------------------------------------------------------------------
locals {
  seed_inventory = {
    "SKU-WIDGET-001" = 500000
    "SKU-WIDGET-002" = 500000
    "SKU-GADGET-010" = 500000
    "SKU-GADGET-011" = 500000
    "SKU-DOODAD-100" = 500000
  }
}

resource "aws_dynamodb_table_item" "inventory_seed" {
  for_each   = local.seed_inventory
  table_name = aws_dynamodb_table.inventory.name
  hash_key   = aws_dynamodb_table.inventory.hash_key

  item = jsonencode({
    sku                = { S = each.key }
    quantity_available = { N = tostring(each.value) }
  })
}
