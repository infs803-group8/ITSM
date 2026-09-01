resource "aws_secretsmanager_secret" "database" {
  name = "${local.name}/database"
}
resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    username = aws_db_instance.mysql.username
    password = random_password.database.result
    host     = aws_db_instance.mysql.address
    port     = aws_db_instance.mysql.port
    database = var.database_name
  })
}
