SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[SavePrepaymentRates](@pkgPurchaseId INT) 
AS 
BEGIN;

	BEGIN TRY;
		DECLARE @wtdAvgPrepaymentRate DECIMAL(12,4) ;

		SET XACT_ABORT ON;
		BEGIN TRANSACTION;

		SELECT 
			loans.pkg_purchase_id
			, loans.pkg_purchase_loan_id
			, accountNumber = loans.fnba_account_number
			, itinStatus = itin.status
			, interestRate = loans.interest_rate_current
			, ltv = CAST(ltv.value AS DECIMAL(15, 2))
			, creditScore = credit.score
			, currentBalance = loans.current_balance
			, treasuryRate = tRates.Tnote_10_year
			, interestRateDelta =  loans.interest_rate_current - tRates.Tnote_10_year
			, state = loans.property_state
			, lienPosition = ISNULL(loans.fnba_lien_position,1)
			, amortizationType = rate.type
			, amortizationPlug = CEILING(y.amortization)
			, x.creditBand
            , x.interestRateBand
            , x.ltvBand
            , x.loanSizeband
            , x.interestRateDeltaBand
            , x.collateralState
            , pprLienPostion = x.lienPosition
            , pprRateType = x.rateType
            , x.overallAverage
		INTO #loans
		FROM fnba.pkg_purchase packages
		JOIN fnba.pkg_purchase_loan loans
			ON loans.pkg_purchase_id = packages.pkg_purchase_id
		CROSS APPLY (SELECT CAST(x.date_of_rate AS DATE),x.Tnote_10_year
				FROM notedb.fnba.arm_rates x
				WHERE x.Tnote_10_year IS NOT NULL
				AND x.date_of_rate = (SELECT MAX(date_of_rate) FROM notedb.fnba.arm_rates WHERE Tnote_10_year IS NOT NULL AND x.date_of_rate <= packages.entry_date))
				AS tRates(dateOfRate, Tnote_10_year)
		CROSS APPLY (SELECT CASE 
								WHEN loans.fnba_credit_score > 0 THEN loans.fnba_credit_score
								WHEN loans.blended_recent_credit > 0 THEN loans.blended_recent_credit
								WHEN loans.credit_bor_recent>0 THEN loans.credit_bor_recent
								WHEN loans.credit_bor_original >0 THEN loans.credit_bor_original
								ELSE 555
							END) AS credit(score)
		CROSS APPLY (SELECT CASE 
								WHEN loans.ltv_recent_bpo>0 THEN loans.ltv_recent_bpo
								WHEN loans.fnba_cltv > 0 THEN loans.fnba_cltv
								WHEN loans.seller_recent_bpo > 0 THEN loans.current_balance/loans.seller_recent_bpo
								WHEN loans.sale_price_original > 0 THEN loans.current_balance/loans.sale_price_original
								ELSE NULL
							END) AS ltv(value)
		CROSS APPLY (SELECT IIF(ISNULL(loans.rate_type,'Fixed') LIKE('F%'), 'FXD', 'ARM')) AS rate(type)
		CROSS APPLY(SELECT IIF(loans.borrower_ssn LIKE('9%'), 'ITIN', 'Not ITIN')) AS itin(status)
		CROSS APPLY bid.ExpectedPrepaymentRate(itin.status, 
													credit.score,
														loans.interest_rate_current,
														ltv.value,
														loans.current_balance, 
														loans.interest_rate_current - tRates.Tnote_10_year,
														loans.property_state,
														ISNULL(loans.fnba_lien_position,1),
														rate.type) x
		CROSS APPLY (SELECT utilities.Amortize(loans.current_balance, 
												loans.pandi_current * x.overallAverage, 
												loans.interest_rate_current, 
												12)) y(amortization)
		WHERE packages.pkg_purchase_id = @pkgPurchaseId

		UPDATE a
		SET a.amortizationPlug = b.amortizationPlug,
			a.prepaymentRate = b.overallAverage
		FROM fnba.pkg_purchase_loan a
		JOIN #loans b
		ON b.pkg_purchase_loan_id = a.pkg_purchase_loan_id;

		DELETE bid.LoanPrepaymentRateLog
		WHERE pkg_purchase_id=@pkgPurchaseId

		INSERT INTO bid.LoanPrepaymentRateLog(
			pkg_purchase_loan_id,
			pkg_purchase_id,
			creditBand,
			interestRateBand,
			ltvBand,
			loanSizeBand,
			interestRateDeltaBand,
			collateralState,
			lienPosition,
			rateType)
		SELECT 
			pkg_purchase_loan_id,
			pkg_purchase_id,
			creditBand,
			interestRateBand,
			ltvBand,
			loanSizeBand,
			interestRateDeltaBand,
			collateralState,
			pprLienPostion,
			pprRateType
		FROM #loans

		SELECT @wtdAvgPrepaymentRate=SUM(prepaymentRate*current_balance)/SUM(current_balance) 
		FROM fnba.pkg_purchase_loan 
		WHERE pkg_purchase_id=@pkgPurchaseId;

		UPDATE fnba.pkg_purchase
		SET wtdAvgPrepaymentRate=@wtdAvgPrepaymentRate
		WHERE pkg_purchase_id=@pkgPurchaseId;

		COMMIT TRANSACTION;

	END TRY
	BEGIN CATCH

		DECLARE @errorMessage VARCHAR(MAX) = ERROR_MESSAGE();
		IF (@@TRANCOUNT > 0) ROLLBACK TRANSACTION;
		THROW 50000,@errorMessage,1;

	END CATCH;

END;
GO