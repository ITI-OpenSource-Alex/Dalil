output "zone_id" {
  description = "Created or supplied Route 53 hosted zone ID."
  value       = local.zone_id
}

output "name_servers" {
  description = "Authoritative name servers when this module creates the zone."
  value       = try(aws_route53_zone.this[0].name_servers, [])
}
