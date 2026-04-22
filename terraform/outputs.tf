output "public_ip" {
  description = "EC2 public IP — point DNS or load balancer here"
  value       = aws_instance.app.public_ip
}

output "ssh_command" {
  description = "SSH into instance"
  value       = "ssh -i ~/.ssh/your_key ec2-user@${aws_instance.app.public_ip}"
}

output "app_url" {
  value = "http://${aws_instance.app.public_ip}:3000"
}

output "grafana_url" {
  value = "http://${aws_instance.app.public_ip}:3001"
}

output "prometheus_url" {
  value = "http://${aws_instance.app.public_ip}:9090"
}
