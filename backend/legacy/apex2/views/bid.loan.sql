SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE VIEW [bid].[loan]
AS

SELECT pkgPurchaseLoan.pkg_purchase_loan_id AS loanId,
	   pkgPurchaseLoan.pkg_purchase_id AS bidId,
	   pkgPurchaseLoan.account_number AS sellerLoanNumber,
	   pkgPurchaseLoan.borrower_last_name AS borrowerLastName,
	   pkgPurchaseLoan.current_balance AS currentBalance,
	   pkgPurchaseLoan.property_address AS propertyAddress,
	   pkgPurchaseLoan.credit_bor_recent AS recentCredit,
	   pkgPurchaseLoan.ltv_used_for_pricing AS ltv,
	   pkgPurchaseLoan.final_price_with_itv_cap AS price,
	   pkgPurchaseLoan.cents_on_the_dollar AS totalBid,
	   pkgPurchaseLoan.fnba_account_number AS accountNumber,
	   pricingStatus.pricing_status AS loanStatus,
	   analystComments.field_value AS analystComments,
	   bidState.name AS bidName,
	   loanBrokerFees.brokerId,
	   brokers.name AS brokerName,
	   loanBrokerFees.feePercentage AS brokerFeePercentage,
	   pkgPurchaseLoan.pricing_status_id AS loanStatusId,
	   pkgPurchaseLoan.final_discount_or_premium AS discount,
	   pkgPurchaseLoan.cents_on_the_dollar - COALESCE(loanBrokerFees.feePercentage, 0.00) AS sellerBid,
	   pkgPurchaseLoan.property_state AS propertyState,
	   CASE WHEN LEN(RIGHT('000' + COALESCE(pkgPurchaseLoan.borrower_ssn, ''), 9)) = 9 
			THEN RIGHT('000' + pkgPurchaseLoan.borrower_ssn, 9)
			ELSE ''
			END AS borrowerTin,
	   pkgPurchaseLoan.original_balance AS originalBalance,
	   pkgPurchaseLoan.interest_rate_current AS interestRate,
	   pkgPurchaseLoan.next_payment_due AS nextPaymentDue,
	   encompass.loanPurpose(loanPurpose.field_value) AS loanPurpose,
	   encompass.occupancy(pkgPurchaseLoan.occupancy) AS occupancy,
	   encompass.propertyType(pkgPurchaseLoan.property_type) AS propertyType,
	   pkgPurchaseLoan.remaining_term AS remainingTerm,
	   pkgPurchaseLoan.property_city AS propertyCity,
	   CASE WHEN LEN(pkgPurchaseLoan.property_zip_code) >= 3 
			THEN RIGHT('00' + pkgPurchaseLoan.property_zip_code, 5) 
			ELSE '' 
			END AS propertyZipCode,
	   pkgPurchaseLoan.co_borrower_last_name  AS coborrowerLastName,
	   CASE WHEN LEN(RIGHT('000' + COALESCE(pkgPurchaseLoan.co_borrower_ssn, ''), 9)) = 9 
			THEN RIGHT('000' + pkgPurchaseLoan.co_borrower_ssn, 9)
			ELSE ''
			END AS coborrowerTin,
	   pkgPurchaseLoan.first_payment_date AS firstPaymentDate,
	   encompass.lienPosition(COALESCE(pkgPurchaseLoan.fnba_lien_position, 1)) AS lienPosition,
	   CASE WHEN pkgPurchaseLoan.modification_date > '19700101' 
			THEN pkgPurchaseLoan.modification_date 
			ELSE NULL 
			END AS modificationDate,
	   pkgPurchaseLoan.origination_date AS originationDate,
	   pkgPurchaseLoan.pandi_current AS paymentAmount,
	   CASE WHEN pkgPurchaseLoan.fnba_property_evaluation > 0.00 
				THEN pkgPurchaseLoan.fnba_property_evaluation
			WHEN pkgPurchaseLoan.seller_recent_bpo > 0.00
				THEN pkgPurchaseLoan.seller_recent_bpo 
			ELSE pkgPurchaseLoan.appr_value_original 
			END AS appraisedValue,
	   pkgPurchaseLoan.purchase_amount AS purchasePrice,
	   pkgPurchaseLoan.universalLoanIdentifier,
	   pkgPurchaseLoan.falloutReasons,
	   bidState.commitmentNumber,
	   sellers.name AS sellerName,
	   bidState.clientId AS clientId,
	   CASE WHEN pkgPurchaseLoan.original_debt2income < 2 
			THEN pkgPurchaseLoan.original_debt2income * 100 
			ELSE pkgPurchaseLoan.original_debt2income 
			END AS debtToIncome,
	   awarded.count AS awardedStatusCount,
	   priced.count AS pricedStatusCount,
	   'BULK' AS origId,
	   packageLoanOfficer.nickname AS loanOfficerUsername,
	   CAST(ROUND(pkgPurchaseLoan.yield_10_year_amort_assump * 100, 2) AS NUMERIC(12, 2)) AS yieldEightYear,
	   pkgPurchaseLoan.loanAnalystId AS loanAnalystId,
	   loanAnalyst.nickname AS loanAnalystName,
	   CEILING(tools.finance.numberOfPaymentsToFullAmortization(pkgPurchaseLoan.current_balance, pkgPurchaseLoan.pandi_current, pkgPurchaseLoan.interest_rate_current, 12)) AS calculatedRemainingTerm,
	   DATEDIFF(MONTH, CAST(pkgPurchaseLoan.first_payment_date AS DATE), CAST(pkgPurchaseLoan.next_payment_due AS DATE)) AS calculatedSeasoning,
	   pkgPurchaseLoan.original_amortization AS originalTerm,
	   bidState.acceleratedAmortization,
	   pkgPurchaseLoan.rate_type AS rateType,
	   CASE WHEN pkgPurchaseLoan.rate_type LIKE('%fha%') THEN 'FHA' 
			WHEN pkgPurchaseLoan.rate_type LIKE('% va %') 
				 OR 
				 pkgPurchaseLoan.rate_type LIKE('va %') 
				 OR 
				 pkgPurchaseLoan.rate_type LIKE(' va%')
				 OR
				 pkgPurchaseLoan.rate_type = 'va' THEN 'VA' 
			WHEN pkgPurchaseLoan.rate_type LIKE('%usda%') THEN 'USDA' 
			WHEN pkgPurchaseLoan.rate_type LIKE('%heloc%') THEN 'HELOC'
			ELSE '' 
			END AS loanType
FROM fnba.pkg_purchase_loan pkgPurchaseLoan
JOIN bid.bidState bidState
	ON bidState.bidId = pkgPurchaseLoan.pkg_purchase_id
JOIN fnba.pricing_status pricingStatus
	ON pricingStatus.pricing_status_id = pkgPurchaseLoan.pricing_status_id
LEFT JOIN fnba.loan_text analystComments
	ON analystComments.pkg_purchase_loan_id = pkgPurchaseLoan.pkg_purchase_loan_id
	AND analystComments.field_name = 'analyst_comments'
LEFT JOIN bid.loanBrokerFees loanBrokerFees
	ON loanBrokerFees.loanId = pkgPurchaseLoan.pkg_purchase_loan_id
LEFT JOIN mapping.brokers brokers
	ON brokers.brokerId = loanBrokerFees.brokerId
LEFT JOIN mapping.sellers sellers
	ON sellers.seller_id = bidState.sellerId
LEFT JOIN fnba.loan_text loanPurpose
	ON loanPurpose.pkg_purchase_loan_id = pkgPurchaseLoan.pkg_purchase_loan_id
	AND loanPurpose.field_name = 'loan_purpose'
JOIN perdb.fnba.associate packageLoanOfficer
	ON bidState.createdById = packageLoanOfficer.assoc_id
LEFT JOIN perdb.fnba.associate loanAnalyst
	ON loanAnalyst.assoc_id = pkgPurchaseLoan.loanAnalystId
CROSS APPLY(SELECT COUNT(*) FROM fnba.pkg_purchase_loan x WHERE x.pkg_purchase_id = bidState.bidId AND x.pricing_status_id = 19) awarded(count)
CROSS APPLY(SELECT COUNT(*) FROM fnba.pkg_purchase_loan x WHERE x.pkg_purchase_id = bidState.bidId AND x.pricing_status_id = 2) priced(count);

GO