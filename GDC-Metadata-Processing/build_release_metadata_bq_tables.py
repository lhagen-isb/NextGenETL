"""

Copyright 2019, Institute for Systems Biology

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

'''
Make sure the VM has BigQuery and Storage Read/Write permissions!

Extract GDC Metadata into Per-Project/Build File BQ Tables
This is still a work in progress (10/16/19)

NOTE AS CURRENTLY SET UP IT DOES NOT PULL IN GENE EXPRESSION TEXT FILES
Inventory as of Release 18 for files that are not multi-case ("multi" or ";" delimited)
program_name	file_type	data_format	count
BEATAML1.0	simple_somatic_mutation	VCF	103
BEATAML1.0	aligned_reads	BAM	119
CGCI	biospecimen_supplement	BCR PPS XML	120
CGCI	biospecimen_supplement	BCR XML	120
CGCI	biospecimen_supplement	BCR SSF XML	93
CGCI	clinical_supplement	BCR XML	117
CGCI	aligned_reads	BAM	500
CGCI	gene_expression	TSV	226
CGCI	gene_expression	TXT	339
CPTAC	aligned_reads	BAM	3227
CPTAC	annotated_somatic_mutation	VCF	1296
CPTAC	gene_expression	TXT	1551
CPTAC	gene_expression	TSV	1034
CPTAC	simple_somatic_mutation	VCF	1296
CTSP	aligned_reads	BAM	212
CTSP	gene_expression	TSV	82
CTSP	gene_expression	TXT	123
FM	simple_somatic_mutation	VCF	18004
FM	annotated_somatic_mutation	VCF	18004
HCMI	biospecimen_supplement	BCR XML	7
HCMI	annotated_somatic_mutation	VCF	56
HCMI	aligned_reads	BAM	84
HCMI	gene_expression	TXT	42
HCMI	gene_expression	TSV	28
HCMI	simple_somatic_mutation	VCF	56
MMRF	annotated_somatic_mutation	VCF	4368
MMRF	aligned_reads	BAM	6577
MMRF	gene_expression	TXT	2577
MMRF	gene_expression	TSV	1718
MMRF	simple_somatic_mutation	VCF	4368
NCICCR	aligned_reads	BAM	2400
NCICCR	gene_expression	TXT	1443
NCICCR	gene_expression	TSV	962
ORGANOID	aligned_reads	BAM	298
ORGANOID	annotated_somatic_mutation	VCF	65
ORGANOID	gene_expression	TXT	165
ORGANOID	gene_expression	TSV	110
ORGANOID	simple_somatic_mutation	VCF	65
TARGET	aligned_reads	BAM	3121
TARGET	gene_expression	TXT	2130
TARGET	annotated_somatic_mutation	VCF	1615
TARGET	mirna_expression	TXT	1170
TARGET	simple_somatic_mutation	VCF	2050
TARGET	gene_expression	TSV	472
TCGA	aligned_reads	BAM	44873
TCGA	biospecimen_supplement	BCR XML	11314
TCGA	gene_expression	TXT	33279
TCGA	methylation_beta_value	TXT	12359
TCGA	slide_image	SVS	30072
TCGA	mirna_expression	TXT	22164
TCGA	copy_number_segment	TXT	45258
TCGA	biospecimen_supplement	BCR SSF XML	10557
TCGA	clinical_supplement	BCR XML	11167
TCGA	clinical_supplement	BCR OMF XML	1051
TCGA	biospecimen_supplement	BCR Auxiliary XML	2884
TCGA	simple_somatic_mutation	VCF	44461
TCGA	annotated_somatic_mutation	VCF	44461
VAREPOP	annotated_somatic_mutation	VCF	7
VAREPOP	aligned_reads	BAM	7
VAREPOP	simple_somatic_mutation	VCF	7

Distinct file types:

extract_alignment_file_data_sql:
  simple_somatic_mutation
  annotated_somatic_mutation
  aligned_reads

extract_file_data_sql_slides:
  slide_image

extract_file_data_sql_clinbio:
  biospecimen_supplement
  clinical_supplement

extract_other_file_data_sql:
  copy_number_segment
  gene_expression
  methylation_beta_value
  mirna_expression

Notes:
CGCI (only) has null aliquot IDS for "gene_expression" type (Rel 18)
FM clinbio entries = 0 because they are all multi-case (Rel 17)

'''

import yaml
import sys
import io

from common_etl.support import generic_bq_harness, confirm_google_vm, \
                               bq_harness_with_result, delete_table_bq_job, bq_table_exists

'''
----------------------------------------------------------------------------------------------
The configuration reader. Parses the YAML configuration into dictionaries
'''
def load_config(yaml_config):
    yaml_dict = None
    config_stream = io.StringIO(yaml_config)
    try:
        yaml_dict = yaml.load(config_stream, Loader=yaml.FullLoader)
    except yaml.YAMLError as ex:
        print(ex)

    if yaml_dict is None:
        return None, None, None, None, None, None, None

    return (yaml_dict['files_and_buckets_and_tables'], yaml_dict['steps'], 
            yaml_dict['builds'], yaml_dict['build_tags'], yaml_dict['path_tags'],
            yaml_dict['programs'], yaml_dict['filter_sets'])

'''
----------------------------------------------------------------------------------------------
Figure out the programs represented in the data
'''
def extract_program_names(release_table, do_batch):

    sql = extract_program_names_sql(release_table)
    results = bq_harness_with_result(sql, do_batch)
    retval = []
    for row in results:
        pn = row.program_name
        if pn is not None and pn != "None":
            retval.append(pn.replace(".", "_")) # handles BEATAML1.0 FIXME! Make it general
    return retval

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def extract_program_names_sql(release_table):
    return '''
        SELECT DISTINCT program_name FROM `{0}` # program_name
        '''.format(release_table)

'''
----------------------------------------------------------------------------------------------
BAM and VCF extraction: BAMS, simple somatic, and annotated somatic VCFs in the target table
'''
def extract_aligned_file_data(release_table, program_name, sql_dict, target_dataset, dest_table, do_batch):

    sql = extract_alignment_file_data_sql(release_table, program_name, sql_dict)
    print(sql)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)


'''
----------------------------------------------------------------------------------------------
build the total filter term:
'''
def build_sql_where_clause(program_name, sql_dict):
    print("_________BUILD_WHERE_________")
    print(sql_dict)


    or_terms = []
    or_filter_list = sql_dict['or_filters'] if 'or_filters' in sql_dict else []
    for pair in or_filter_list:
        for key_vals in pair.items():
            or_terms.append('( a.{0} {1} "{2}" )'.format(key_vals[0], key_vals[1][0], key_vals[1][1]))
    print(len(or_terms))
    or_filter_term = " OR ".join(or_terms)

    print(or_filter_term)

    # Some legacy TCGA images don't even have a TCGA program_name! So make it optional:
    and_terms = []
    if program_name is not None:
        prog_term = "(a.program_name = '{0}')".format(program_name)
        and_terms.append(prog_term)

    and_filter_list = sql_dict['and_filters'] if 'and_filters' in sql_dict else []

    if len(or_terms) > 0:
        and_terms.append('( {} )'.format(or_filter_term))
    for pair in and_filter_list:
        for key_vals in pair.items():
            and_terms.append('( a.{0} {1} "{2}" )'.format(key_vals[0], key_vals[1][0], key_vals[1][1]))
    and_filter_term = " AND ".join(and_terms)

    if 'type_term' in sql_dict:
        type_term = sql_dict['type_term']
        with_table = type_term.format("a")
        full_type_term = "{0} as data_type".format(with_table)
    else:
        full_type_term = "a.data_type"

    print(and_filter_term)
    return and_filter_term, full_type_term

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def extract_alignment_file_data_sql(release_table, program_name, sql_dict):

    and_filter_term, full_type_term = build_sql_where_clause(program_name, sql_dict)


    # (a.file_type = "copy_number_segment"
    # OR
    # a.file_type = "gene_expression"
    # OR
    # a.file_type = "methylation_beta_value"
    # OR
    # # CGCI has null aliquot IDS for gene_expression type:
    # a.file_type = "mirna_expression" )  # AND
    # # ( a.associated_entities__entity_type ="aliquot" )

    return '''
        SELECT 
            a.file_id as file_gdc_id,
            a.case_gdc_id,
            # When there are two aliquots (tumor/normal VCFs, it looks like the target table is using the second
            # no matter what it is...
            # WARNING! Some legacy files (entity_type = "aliquot;case") are of the form "caseID;aliquot1ID;aliquot2ID"
            CASE WHEN (STRPOS(a.associated_entities__entity_gdc_id, ";") != 0)
                 THEN REGEXP_EXTRACT(a.associated_entities__entity_gdc_id,
                                     r"^[a-zA-Z0-9-]+;([a-zA-Z0-9-]+)$") 
              ELSE a.associated_entities__entity_gdc_id
            END as aliquot_id,
            a.project_short_name, # TCGA-OV
            # Some names have two hyphens, not just one:
            CASE WHEN (a.project_short_name LIKE '%-%-%') THEN
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+)-[A-Z0-9]+$")
                 ELSE
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+$)")
            END as disease_code, # OV
            a.program_name, # TCGA
            # Everybody except TCGA ACTIVE uses the input "data_type" for "data_type"
            # TCGA active uses the "experimental_strategy" for "data_type"
            {0}, # The variable type_term
            a.data_category,
            a.experimental_strategy,
            # Using a keyword for a column is bogus, but it was like this already:
            a.file_type as `type`,
            a.file_size,
            a.data_format,
            a.platform,
            CAST(null AS STRING) as file_name_key,
            a.index_file_gdc_id as index_file_id,
            CAST(null AS STRING) as index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{1}` AS a
        WHERE {2} AND (a.associated_entities__entity_type = "aliquot")
        '''.format(full_type_term, release_table, and_filter_term)

'''
----------------------------------------------------------------------------------------------
Slide extraction
'''
def extract_slide_file_data(release_table, program_name, sql_dict, target_dataset, dest_table, do_batch):

    sql = extract_file_data_sql_slides(release_table, program_name, sql_dict)
    print(sql)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''


def extract_file_data_sql_slides(release_table, program_name, sql_dict):

    # 10,000+ Legacy TCGA slides have no program name! Accommodate this bogosity:
    use_name = None if 'drop_program' in sql_dict and sql_dict['drop_program'] else program_name
    and_filter_term, full_type_term = build_sql_where_clause(use_name, sql_dict)

    return '''
        SELECT 
            a.file_id as file_gdc_id,
            a.case_gdc_id,
            a.associated_entities__entity_gdc_id as slide_id,
            a.project_short_name, # TCGA-OV
            # Some names have two hyphens, not just one:
            CASE WHEN (a.project_short_name LIKE '%-%-%') THEN
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+)-[A-Z0-9]+$")
                 ELSE
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+$)")
            END as disease_code, # OV
            a.program_name, # TCGA
            {0}, # The variable type_term
            a.data_category,
            CAST(null AS STRING) as experimental_strategy,
            # Using a keyword for a column is bogus, but it was like this already:
            a.file_type as `type`,
            a.file_size,
            a.data_format,
            a.platform,
            CAST(null AS STRING) as file_name_key,
            CAST(null AS STRING) as index_file_id,
            CAST(null AS STRING) as index_file_name_key,
            CAST(null AS INT64) as index_file_size,
            a.access,
            a.acl,
            # Some legacy entries have no case ID or sample ID, it is embedded in the file name, and
            # we need to pull that out to get that info
            CASE WHEN (a.case_gdc_id IS NULL) THEN
                   REGEXP_EXTRACT(a.file_name, r"^([A-Z0-9-]+).+$")
                ELSE
                   CAST(null AS STRING)
            END as slide_barcode
        FROM `{1}` AS a
        WHERE {2}
        '''.format(full_type_term, release_table, and_filter_term)


'''
----------------------------------------------------------------------------------------------
Slide repair. Legacy archive is full of bogus slide files which only can be identified by the file name.
These tables do not hold the case id, nor the program or disease name. Fix this bogosity!
'''
def repair_slide_file_data(case_table, broken_table, target_dataset, dest_table, do_batch):

    sql = repair_missing_case_data_sql_slides(case_table, broken_table)
    print(sql)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above. Note this processing ends up throwing away one slide from case TCGA-08-0384, which
actaully does not appear in the case file going back to at least release 6.
'''

def repair_missing_case_data_sql_slides(case_table, broken_table):

    return '''
        WITH
           a1 AS
          (SELECT case_gdc_id, project_id, case_barcode,
             REGEXP_EXTRACT(project_id, r"^[A-Z]+-([A-Z]+$)") as disease_code,
             program_name # TCGA
           FROM `{0}`
           ),
          a2 AS
          (SELECT *
           FROM `{1}` WHERE slide_barcode IS NOT NULL
          )
        SELECT
            a2.file_gdc_id,
            a1.case_gdc_id,
            a2.slide_id,
            a1.project_id as project_short_name,
            a1.disease_code,
            a1.program_name,
            a2.data_type,
            a2.data_category,
            a2.experimental_strategy,
            a2.type,
            a2.file_size,
            a2.data_format,
            a2.platform,
            a2.file_name_key,
            a2.index_file_id,
            a2.index_file_name_key,
            a2.index_file_size,
            a2.access,
            a2.acl,
            a2.slide_barcode
        FROM a2 JOIN a1 ON a1.case_barcode = REGEXP_EXTRACT(a2.slide_barcode, r"^(TCGA-[A-Z0-9][A-Z0-9]-[A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9])")
        UNION ALL
        SELECT * FROM `{1}` WHERE slide_barcode IS NULL
        '''.format(case_table, broken_table)


'''
----------------------------------------------------------------------------------------------
Clinical extraction (CLIN and BIO files):
'''


def extract_clinbio_file_data(release_table, program_name, sql_dict, target_dataset, dest_table, do_batch):
    sql = extract_file_data_sql_clinbio(release_table, program_name, sql_dict)
    print(sql)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''


def extract_file_data_sql_clinbio(release_table, program_name, sql_dict):

    and_filter_term, full_type_term = build_sql_where_clause(program_name, sql_dict)

    return '''
        SELECT 
            a.file_id as file_gdc_id,
            a.case_gdc_id,
            a.associated_entities__entity_gdc_id as case_id,
            a.project_short_name, # TCGA-OV
            # Some names have two hyphens, not just one:
            CASE WHEN (a.project_short_name LIKE '%-%-%') THEN
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+)-[A-Z0-9]+$")
                 ELSE
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+$)")
            END as disease_code, # OV
            a.program_name, # TCGA
            {0}, # The variable type_term
            a.data_category,
            a.experimental_strategy,
            # Using a keyword for a column is bogus, but it was like this already:
            a.file_type as `type`,
            a.file_size,
            a.data_format,
            a.platform,
            CAST(null AS STRING) as file_name_key,
            CAST(null AS STRING) as index_file_id,
            CAST(null AS STRING) as index_file_name_key,
            CAST(null AS INT64) as index_file_size,
            a.access,
            a.acl
        FROM `{1}` AS a
        WHERE {2}
        '''.format(full_type_term, release_table, and_filter_term)


'''
----------------------------------------------------------------------------------------------
Various other files
'''


def extract_other_file_data(release_table, program_name, sql_dict, barcode, target_dataset, dest_table, do_batch):

    sql = extract_other_file_data_sql(release_table, program_name, sql_dict, barcode)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''


def extract_other_file_data_sql(release_table, program_name, sql_dict, barcode):

    and_filter_term, full_type_term = build_sql_where_clause(program_name, sql_dict)
    use_and = and_filter_term if and_filter_term == "" else "{} AND".format(and_filter_term)

    return '''
        SELECT
            a.file_id as file_gdc_id,
            a.case_gdc_id,
            # When there are two aliquots (tumor/normal VCFs, it looks like the target table is using the second
            # no matter what it is...
            CASE WHEN (STRPOS(a.associated_entities__entity_gdc_id, ";") != 0)
                 THEN REGEXP_EXTRACT(a.associated_entities__entity_gdc_id,
                                     r"^[a-zA-Z0-9-]+;([a-zA-Z0-9-]+)$")
              ELSE a.associated_entities__entity_gdc_id
            END as {3}_id,
            a.project_short_name, # TCGA-OV
            # Some names have two hyphens, not just one:
            CASE WHEN (a.project_short_name LIKE '%-%-%') THEN
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+)-[A-Z0-9]+$")
                 ELSE
                   REGEXP_EXTRACT(a.project_short_name, r"^[A-Z]+-([A-Z]+$)")
            END as disease_code, # OV
            a.program_name, # TCGA
            {0}, # The variable type_term
            a.data_category,
            a.experimental_strategy,
            a.file_type as `type`,
            a.file_size,
            a.data_format,
            a.platform,
            CAST(null AS STRING) as file_name_key,
            a.index_file_gdc_id as index_file_id,
            CAST(null AS STRING) as index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{1}` AS a
        # The whole deal here is to only use files associated with a single case ID. Null ids and
        # multiple IDs means we ignore the file.
        WHERE (a.case_gdc_id IS NOT NULL) AND
              (a.case_gdc_id NOT LIKE '%;%') AND
              (a.case_gdc_id != 'multi') AND {2}
              (a.associated_entities__entity_type = "{3}")
        '''.format(full_type_term, release_table, use_and, barcode)

'''
----------------------------------------------------------------------------------------------
Get case barcodes associated with the clinical files:
'''


def extract_case_barcodes(release_table, aliquot_2_case_table, program_name, target_dataset, dest_table, do_batch):

    sql = case_barcodes_sql(release_table, aliquot_2_case_table, program_name)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def case_barcodes_sql(release_table, aliquot_2_case_table, program_name):
    return '''
        WITH
        a1 AS (SELECT DISTINCT case_gdc_id, case_barcode FROM `{1}` GROUP BY case_gdc_id, case_barcode)            
        SELECT
            a.file_gdc_id,
            a.case_gdc_id,
            a1.case_barcode,
            "NA" as sample_gdc_id,
            "NA" as sample_barcode,
            a.project_short_name,
            a.disease_code,
            a.program_name,
            # FIXME DO WE WANT TO DROP THIS ARCHIVAL FIX??? Yes...
            # Archival table had null in this slot:
            # CAST(null AS STRING) as data_type,
            a.data_type,
            a.data_category,
            a.experimental_strategy,
            a.type,
            a.file_size,
            a.data_format,
            a.platform,
            a.file_name_key,
            a.index_file_id,
            a.index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{0}` AS a JOIN a1 ON a.case_id = a1.case_gdc_id
        '''.format(release_table, aliquot_2_case_table, program_name)


'''
----------------------------------------------------------------------------------------------
Get sample and case barcodes associated with the sequence files:
'''
def extract_aliquot_barcodes(release_table, aliquot_2_case_table, program_name, target_dataset, dest_table, do_batch):

    sql = aliquot_barcodes_sql(release_table, aliquot_2_case_table, program_name)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def aliquot_barcodes_sql(release_table, aliquot_2_case_table, program_name):

    return '''
        SELECT
            a.file_gdc_id,
            a.case_gdc_id,
            c.case_barcode,
            c.sample_gdc_id,
            c.sample_barcode,
            a.project_short_name,
            a.disease_code,
            a.program_name,
            a.data_type,
            a.data_category,
            a.experimental_strategy,
            a.type,
            a.file_size,
            a.data_format,
            a.platform,
            a.file_name_key,
            a.index_file_id,
            a.index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{0}` AS a JOIN `{1}` AS c ON a.aliquot_id = c.aliquot_gdc_id
        '''.format(release_table, aliquot_2_case_table, program_name)


'''
----------------------------------------------------------------------------------------------
Get sample and case barcodes associated with the slide files:
'''
def extract_slide_barcodes(release_table, slide_2_case_table, program_name, target_dataset, dest_table, do_batch):

    sql = slide_barcodes_sql(release_table, slide_2_case_table, program_name)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def slide_barcodes_sql(release_table, slide_2_case_table, program_name):

    return '''
        # Some slides have two entries in the slide_2_case table if they depict two portions. Remove the dups:
        WITH a1 as (
        SELECT DISTINCT
            case_barcode,
            sample_gdc_id,
            sample_barcode,
            slide_gdc_id,
            slide_barcode
        FROM `{1}` GROUP BY case_barcode, sample_gdc_id, sample_barcode, slide_gdc_id, slide_barcode)
        SELECT
            a.file_gdc_id,
            a.case_gdc_id,
            a1.case_barcode,
            a1.sample_gdc_id,
            a1.sample_barcode,
            a.project_short_name,
            a.disease_code,
            a.program_name,
            a.data_type,
            a.data_category,
            a.experimental_strategy,
            a.type,
            a.file_size,
            a.data_format,
            a.platform,
            a.file_name_key,
            a.index_file_id,
            a.index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{0}` AS a JOIN a1 ON a.slide_barcode = a1.slide_barcode
        UNION DISTINCT
        SELECT
            a.file_gdc_id,
            a.case_gdc_id,
            a1.case_barcode,
            a1.sample_gdc_id,
            a1.sample_barcode,
            a.project_short_name,
            a.disease_code,
            a.program_name,
            a.data_type,
            a.data_category,
            a.experimental_strategy,
            a.type,
            a.file_size,
            a.data_format,
            a.platform,
            a.file_name_key,
            a.index_file_id,
            a.index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{0}` AS a JOIN a1 ON a.slide_id = a1.slide_gdc_id
        '''.format(release_table, slide_2_case_table, program_name)

'''
----------------------------------------------------------------------------------------------
Glue different tables together:
'''
def build_union(table_list, target_dataset, dest_table, do_batch):

    sql = union_sql(table_list)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)


'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def union_sql(table_list):
    terms = []
    for table in table_list:
        terms.append("SELECT * FROM `{0}`".format(table))
    filter_term = " UNION ALL ".join(terms)
    return filter_term

'''
----------------------------------------------------------------------------------------------
Final Step:
Get the URIs in from the manifest file:
Two passes used, first for all files, second for index files:
'''
def install_uris(union_table, mapping_table, target_dataset, dest_table, do_batch):
    
    sql = install_uris_sql(union_table, mapping_table)
    return generic_bq_harness(sql, target_dataset, dest_table, do_batch, True)

'''
----------------------------------------------------------------------------------------------
SQL for above:
'''
def install_uris_sql(union_table, mapping_table):
    return '''
        WITH a1 as (
        SELECT
            a.file_gdc_id,
            a.case_gdc_id,
            a.case_barcode,
            a.sample_gdc_id,
            a.sample_barcode,
            a.project_short_name,
            a.disease_code,
            a.program_name,
            a.data_type,
            a.data_category,
            a.experimental_strategy,
            a.type,
            a.file_size,
            a.data_format,
            a.platform,
            c.gcs_path as file_name_key,
            a.index_file_id,
            a.index_file_name_key,
            a.index_file_size,
            a.access,
            a.acl
        FROM `{0}` AS a LEFT OUTER JOIN `{1}` AS c ON a.file_gdc_id = c.file_uuid )
        
        SELECT
            a1.file_gdc_id,
            a1.case_gdc_id,
            a1.case_barcode,
            a1.sample_gdc_id,
            a1.sample_barcode,          
            a1.project_short_name,
            a1.disease_code,
            a1.program_name,
            a1.data_type,
            a1.data_category,
            a1.experimental_strategy,
            a1.type,
            a1.file_size,
            a1.data_format,
            a1.platform,
            a1.file_name_key,
            a1.index_file_id,
            c.gcs_path as index_file_name_key,
            a1.index_file_size,
            a1.access,
            a1.acl
        FROM a1 LEFT OUTER JOIN `{1}` AS c ON a1.index_file_id = c.file_uuid
        '''.format(union_table, mapping_table)


'''
----------------------------------------------------------------------------------------------
Do all the steps for a given dataset and build

sequence
'''


def do_dataset_and_build(steps, build, build_tag, path_tag, sql_dict, dataset, params):

    file_table = "{}_{}".format(params['FILE_TABLE'], build_tag)

    #
    # Pull stuff from rel:
    #
     
    if 'pull_slides' in steps and 'slide' in sql_dict:
        step_zero_table = "{}_{}_{}".format(dataset, build, params['SLIDE_STEP_0_TABLE'])
        success = extract_slide_file_data(file_table, dataset, sql_dict['slide'], params['TARGET_DATASET'],
                                          step_zero_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} pull_slides job failed".format(dataset, build))
            return False

        step_one_table = "{}_{}_{}".format(dataset, build, params['SLIDE_STEP_1_TABLE'])
        case_table = "{}_{}_{}".format(dataset, build, params['CASE_TABLE'])
        success = repair_slide_file_data(case_table, step_zero_table,
                                         params['TARGET_DATASET'], step_one_table, params['BQ_AS_BATCH'])
        if not success:
            print("{} {} repair slides sub-job failed".format(dataset, build))
            return False

    if 'pull_align' in steps and 'sequence' in sql_dict:
        step_one_table = "{}_{}_{}".format(dataset, build, params['ALIGN_STEP_1_TABLE'])
        success = extract_aligned_file_data(file_table, dataset, sql_dict['sequence'], params['TARGET_DATASET'],
                                            step_one_table, params['BQ_AS_BATCH'])        
        if not success:
            print("{} {} pull_align job failed".format(dataset, build))
            return False    

    if 'pull_clinbio' in steps and 'bioclin' in sql_dict:
        step_one_table = "{}_{}_{}".format(dataset, build, params['CLINBIO_STEP_1_TABLE'])
        success = extract_clinbio_file_data(file_table, dataset, sql_dict['bioclin'], params['TARGET_DATASET'],
                                            step_one_table, params['BQ_AS_BATCH']) 
        if not success:
            print("{} {} pull_clinbio job failed".format(dataset, build))
            return False

    if 'pull_other_aliquot' in steps and 'other_aliquot' in sql_dict:
        step_one_table = "{}_{}_{}".format(dataset, build, params['OTHER_ALIQUOT_STEP_1_TABLE'])
        success = extract_other_file_data(file_table, dataset, sql_dict['other_aliquot'], "aliquot", params['TARGET_DATASET'],
                                            step_one_table, params['BQ_AS_BATCH'])
        if not success:
            print("{} {} pull_other job failed".format(dataset, build))
            return False

    if 'pull_other_case' in steps and 'other_case' in sql_dict:
        step_one_table = "{}_{}_{}".format(dataset, build, params['OTHER_CASE_STEP_1_TABLE'])
        success = extract_other_file_data(file_table, dataset, sql_dict['other_case'], "case", params['TARGET_DATASET'],
                                            step_one_table, params['BQ_AS_BATCH'])
        if not success:
            print("{} {} pull_other job failed".format(dataset, build))
            return False


    if 'slide_barcodes' in steps and 'slide' in sql_dict:
        in_table = '{}.{}.{}'.format(params['WORKING_PROJECT'], 
                                     params['TARGET_DATASET'], 
                                     "{}_{}_{}".format(dataset, build, params['SLIDE_STEP_1_TABLE']))
        step_two_table = "{}_{}_{}".format(dataset, build, params['SLIDE_STEP_2_TABLE'])
        success = extract_slide_barcodes(in_table, params['SLIDE_TABLE'], dataset, params['TARGET_DATASET'], 
                                         step_two_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} slide_barcodes job failed".format(dataset, build))
            return False
        
    if 'align_barcodes' in steps and 'sequence' in sql_dict:
        in_table = '{}.{}.{}'.format(params['WORKING_PROJECT'], 
                                     params['TARGET_DATASET'], 
                                     "{}_{}_{}".format(dataset, build, params['ALIGN_STEP_1_TABLE']))

        step_two_table = "{}_{}_{}".format(dataset, build, params['ALIGN_STEP_2_TABLE'])
        success = extract_aliquot_barcodes(in_table, params['ALIQUOT_TABLE'], dataset, params['TARGET_DATASET'], 
                                           step_two_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} align_barcodes job failed".format(dataset, build))
            return False

    if 'clinbio_barcodes' in steps and 'bioclin' in sql_dict:
        in_table = '{}.{}.{}'.format(params['WORKING_PROJECT'], 
                                     params['TARGET_DATASET'], 
                                     "{}_{}_{}".format(dataset, build, params['CLINBIO_STEP_1_TABLE']))

        step_two_table = "{}_{}_{}".format(dataset, build, params['CLINBIO_STEP_2_TABLE'])
        success = extract_case_barcodes(in_table, params['ALIQUOT_TABLE'], dataset, params['TARGET_DATASET'], 
                                        step_two_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} clin_barcodes job failed".format(dataset, build))
            return False                 

    if 'other_aliquot_barcodes' in steps and 'other_aliquot' in sql_dict:
        in_table = '{}.{}.{}'.format(params['WORKING_PROJECT'],
                                     params['TARGET_DATASET'],
                                     "{}_{}_{}".format(dataset, build, params['OTHER_ALIQUOT_STEP_1_TABLE']))
        step_two_table = "{}_{}_{}".format(dataset, build, params['OTHER_ALIQUOT_STEP_2_TABLE'])
        success = extract_aliquot_barcodes(in_table, params['ALIQUOT_TABLE'], dataset, params['TARGET_DATASET'],
                                           step_two_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} other_barcodes job failed".format(dataset, build))
            return False

    if 'other_case_barcodes' in steps and 'other_case' in sql_dict:
        in_table = '{}.{}.{}'.format(params['WORKING_PROJECT'],
                                     params['TARGET_DATASET'],
                                     "{}_{}_{}".format(dataset, build, params['OTHER_CASE_STEP_1_TABLE']))
        step_two_table = "{}_{}_{}".format(dataset, build, params['OTHER_CASE_STEP_2_TABLE'])
        success = extract_case_barcodes(in_table, params['ALIQUOT_TABLE'], dataset, params['TARGET_DATASET'],
                                        step_two_table, params['BQ_AS_BATCH'])

        if not success:
            print("{} {} other_barcodes job failed".format(dataset, build))
            return False


    if 'union_tables' in steps:
        table_list = []

        union_table_tags = ['SLIDE_STEP_2_TABLE', 'ALIGN_STEP_2_TABLE', 'CLINBIO_STEP_2_TABLE',
                            'OTHER_CASE_STEP_2_TABLE' ,'OTHER_ALIQUOT_STEP_2_TABLE']

        for tag in union_table_tags:
            if tag in params:
                table_name = "{}_{}_{}".format(dataset, build, params[tag])
                if bq_table_exists(params['TARGET_DATASET'], table_name):
                    full_table = '{}.{}.{}'.format(params['WORKING_PROJECT'], params['TARGET_DATASET'], table_name)
                    table_list.append(full_table)

        union_table = "{}_{}_{}".format(dataset, build, params['UNION_TABLE'])
        success = build_union(table_list,
                              params['TARGET_DATASET'], union_table, params['BQ_AS_BATCH'])
        if not success:
            print("{} {} union_tables job failed".format(dataset, build))
            return False

    # Merge the URL info into the final table we are building:

    if 'create_final_table' in steps:
        union_table = '{}.{}.{}'.format(params['WORKING_PROJECT'], 
                                        params['TARGET_DATASET'], 
                                        "{}_{}_{}".format(dataset, build, params['UNION_TABLE']))        
        success = install_uris(union_table, "{}{}".format(params['UUID_2_URL_TABLE'], path_tag),
                               params['TARGET_DATASET'], 
                               "{}_{}_{}".format(dataset, build, params['FINAL_TABLE']), params['BQ_AS_BATCH'])
        if not success:
            print("{} {} create_final_table job failed".format(dataset, build))
            return False

    #
    # Clear out working temp tables:
    #

    if 'dump_working_tables' in steps:
        dump_tables = []
        dump_table_tags = ['SLIDE_STEP_0_TABLE', 'SLIDE_STEP_1_TABLE', 'SLIDE_STEP_2_TABLE', 'ALIGN_STEP_1_TABLE',
                           'ALIGN_STEP_2_TABLE', 'CLINBIO_STEP_1_TABLE', 'CLINBIO_STEP_2_TABLE',
                           'OTHER_CASE_STEP_1_TABLE', 'OTHER_CASE_STEP_2_TABLE',
                           'OTHER_ALIQUOT_STEP_1_TABLE', 'OTHER_ALIQUOT_STEP_2_TABLE', 'UNION_TABLE']
        for tag in dump_table_tags:
            table_name = "{}_{}_{}".format(dataset, build, params[tag])
            if bq_table_exists(params['TARGET_DATASET'], table_name):
                dump_tables.append(table_name)

        for table in dump_tables:
            delete_table_bq_job(params['TARGET_DATASET'], table)

    #
    # Done!
    #
    
    return True

'''
----------------------------------------------------------------------------------------------
Main Control Flow
Note that the actual steps run are configured in the YAML input! This allows you to e.g. skip previously run steps.
'''

def main(args):

    if not confirm_google_vm():
        print('This job needs to run on a Google Cloud Compute Engine to avoid storage egress charges [EXITING]')
        return

    if len(args) != 2:
        print(" ")
        print(" Usage : {} <configuration_yaml>".format(args[0]))
        return

    print('job started')

    #
    # Get the YAML config loaded:
    #

    with open(args[1], mode='r') as yaml_file:
        params, steps, builds, build_tags, path_tags, programs, filter_sets = load_config(yaml_file.read())

    if params is None:
        print("Bad YAML load")
        return

    for build, build_tag, path_tag in zip(builds, build_tags, path_tags):
        file_table = "{}_{}".format(params['FILE_TABLE'], build_tag)
        datasets = programs
        if datasets is None:
            datasets = extract_program_names(file_table, params['BQ_AS_BATCH'])
        for dataset in datasets:
            if dataset in filter_sets and build_tag in filter_sets[dataset]:
                sql_dict = filter_sets[dataset][build_tag]
            else:
                sql_dict = {}
            print(sql_dict)
            print ("Processing build {} ({}) for program {}".format(build, build_tag, dataset))
            ok = do_dataset_and_build(steps, build, build_tag, path_tag, sql_dict, dataset, params)
            if not ok:
                return
            
    print('job completed')

if __name__ == "__main__":
    main(sys.argv)

