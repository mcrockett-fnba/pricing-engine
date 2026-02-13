SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO

CREATE VIEW [bid].[bidState]
AS 

WITH _loans AS
(
	SELECT pkg_purchase_id,
		   SUM(current_balance) AS currentBalance, 
		   COUNT(*) AS loanCount
	FROM fnba.pkg_purchase_loan  
	GROUP BY pkg_purchase_id
)
SELECT pkgPurchase.pkg_purchase_id AS bidId,
	   pkgPurchase.name,
	   pkgPurchase.created_by_id AS createdById,
	   pkgPurchase.entry_date AS createdOn,
	   pkgPurchase.poolPricingStatusId AS bidStatusId,
	   associate.first_name + ' ' + associate.last_name AS createdBy,
	   pricingStatus.pricing_status AS bidStatus,
	   _loans.loancount,
	   _loans.currentBalance,
	   COALESCE(pkgPurchase.isActiveBid, 1) AS isActiveBid,
	   pkgPurchase.seller_id AS sellerId,
	   sellers.name_1 AS sellerName,
	   pkgPurchase.final_price_with_itv_cap AS price,
	   associateSignatures.signature AS letterOfIntentSignature,
	   letterOfIntentSigner.first_name + ' ' + letterOfIntentSigner.last_name AS letterOfIntentSigner,
	   pkgPurchase.commitmentNumber,
	   externalOrganization.tpoId AS clientId,
	   pkgPurchase.accel_amort_plug_yld_calc AS acceleratedAmortization
FROM fnba.pkg_purchase pkgPurchase
JOIN perdb.fnba.associate associate
	ON associate.assoc_id = pkgPurchase.created_by_id
JOIN fnba.pricing_status pricingStatus
	ON pricingStatus.pricing_status_id = pkgPurchase.poolPricingStatusId
LEFT JOIN notedb.fnba.sellers sellers	
	ON sellers.seller_id = pkgPurchase.seller_id
LEFT JOIN perdb.fnba.associateSignatures associateSignatures
	ON associateSignatures.assoc_id = 3094 -- aparr
LEFT JOIN perdb.fnba.associate letterOfIntentSigner
	ON letterOfIntentSigner.assoc_id = associateSignatures.assoc_id
LEFT JOIN _loans
	ON _loans.pkg_purchase_id = pkgPurchase.pkg_purchase_id
LEFT JOIN encompassCrossRef.tpo.externalOrganization externalOrganization
	ON externalOrganization.ppdCorrSellerId = pkgPurchase.seller_id
	AND externalOrganization.delegated = 1
	AND externalOrganization.isDeleted = 0
	AND externalOrganization.isCorrespondent = 1;

GO