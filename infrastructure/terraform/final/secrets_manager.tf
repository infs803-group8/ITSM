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
    database_url = format("mysql+pymysql://%s:%s@%s:%s/%s",
      aws_db_instance.mysql.username, urlencode(random_password.database.result),
    aws_db_instance.mysql.address, aws_db_instance.mysql.port, var.database_name)
  })
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}
resource "aws_secretsmanager_secret" "jwt" {
  name = "${local.name}/jwt"
}
resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = random_password.jwt.result
}
