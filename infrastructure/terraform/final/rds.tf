resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.database[*].id
}
resource "random_password" "database" {
  length  = 24
  special = false
}
resource "random_password" "cloudfront_origin_header" {
  length  = 32
  special = false
}
resource "aws_db_instance" "mysql" {
  identifier             = local.name
  engine                 = "mysql"
  engine_version         = "8.4"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = var.database_name
  username               = "itsm_admin"
  password               = random_password.database.result
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  skip_final_snapshot    = true
}
