output "certificate_arn" {
  description = "ARN of the imported or validated ACM certificate."
  value = var.certificate_type == "self_signed" ? (
    aws_acm_certificate.self_signed[0].arn
  ) : aws_acm_certificate_validation.public[0].certificate_arn
}
