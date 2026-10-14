variable "region" { type = string }
variable "project" {
  type    = string
  default = "aws-rag"
}
variable "bucket_name" { type = string }
variable "document_prefix" {
  type    = string
  default = "documents/"
}
variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "db_engine_version" {
  description = "Set an available PostgreSQL 16 minor version in your region before apply; the parameter group uses the postgres16 family."
  type        = string
  nullable    = false
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "knowledge_base_arn" {
  description = "Existing conventional VECTOR KB ARN. Use the KB created with docs/aws-setup.md."
  type        = string
  default     = null
}
variable "inference_resource_arns" {
  description = "Selected model or inference profile ARN plus all backing model ARNs for cross-region inference."
  type        = list(string)
  default     = []
}
