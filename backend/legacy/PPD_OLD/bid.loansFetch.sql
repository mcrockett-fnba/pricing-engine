SET QUOTED_IDENTIFIER, ANSI_NULLS ON
GO
CREATE PROCEDURE [bid].[loansFetch]
	@bidId INT,
	@sortBy VARCHAR(100) = NULL,
	@pageShowing INT = NULL,
	@sortDirection VARCHAR(100) = 'ASC',
	@loanStatus VARCHAR(100) = '',
	@searchTextFilter VARCHAR(100) = ''
AS
BEGIN;
 
	DECLARE @statement NVARCHAR(MAX);
	
	CREATE TABLE #loans(loanId INT, bidId INT, sellerLoanNumber VARCHAR(100), borrowerLastName VARCHAR(100), currentBalance NUMERIC(12, 2), propertyAddress VARCHAR(100),	
						recentCredit INT, ltv NUMERIC(12, 7), price NUMERIC(12, 2), totalBid NUMERIC(12, 2), accountNumber INT, loanStatus VARCHAR(100), 
						analystComments VARCHAR(MAX), bidName VARCHAR(100), brokerId INT, brokerName VARCHAR(100), brokerFeePercentage NUMERIC(12, 7), 
						propertyState VARCHAR(100), borrowerTin VARCHAR(100), originalBalance NUMERIC(12, 2), interestRate NUMERIC(12, 7), 
						nextPaymentDue DATE, loanPurpose VARCHAR(100), occupancy VARCHAR(100), propertyType VARCHAR(100), remainingTerm INT, propertyCity VARCHAR(100), 
						propertyZipCode VARCHAR(100), coborrowerLastName VARCHAR(100), coborrowerTin VARCHAR(100), firstPaymentDate DATE, lienPosition VARCHAR(100), 
						modificationDate DATE,	originationDate DATE, paymentAmount NUMERIC(12, 2), appraisedValue NUMERIC(12, 2), purchasePrice NUMERIC(12, 2), 
						universalLoanIdentifier VARCHAR(100), falloutReasons VARCHAR(MAX), sellerName VARCHAR(100), commitmentNumber INT, clientId VARCHAR(100), 
						debtToIncome NUMERIC(12, 7), awardedStatusCount INT, pricedStatusCount INT, origId VARCHAR(100), loanOfficerUsername VARCHAR(100), 
						yieldEightYear NUMERIC(12, 7), loanAnalystName VARCHAR(100), calculatedRemainingTerm INT, calculatedSeasoning INT, originalTerm INT,
						acceleratedAmortization INT, loanType VARCHAR(1000));

	INSERT #loans(loanId, bidId, sellerLoanNumber, borrowerLastName, currentBalance, propertyAddress,	recentCredit, ltv, price, 
				  totalBid, accountNumber, loanStatus, analystComments, bidName, brokerId, brokerName, brokerFeePercentage,	
				  propertyState,borrowerTin, originalBalance, interestRate, nextPaymentDue, loanPurpose, occupancy,
				  propertyType, remainingTerm, propertyCity, propertyZipCode, coborrowerLastName, coborrowerTin, firstPaymentDate,				
				  lienPosition, modificationDate,	originationDate, paymentAmount, appraisedValue, purchasePrice, universalLoanIdentifier,
				  falloutReasons, sellerName, commitmentNumber, clientId, debtToIncome, awardedStatusCount, pricedStatusCount,
				  origId, loanOfficerUsername, yieldEightYear, loanAnalystName, calculatedRemainingTerm, calculatedSeasoning, originalTerm,
				  acceleratedAmortization, loanType)
	SELECT loanId, bidId, sellerLoanNumber, borrowerLastName, currentBalance, propertyAddress,	recentCredit, ltv, price, 
			totalBid, accountNumber, loanStatus, analystComments, bidName, brokerId, brokerName, brokerFeePercentage,	
			propertyState,borrowerTin, originalBalance, interestRate, nextPaymentDue, loanPurpose, occupancy,
			propertyType, remainingTerm, propertyCity, propertyZipCode, coborrowerLastName, coborrowerTin, firstPaymentDate,				
			lienPosition, modificationDate,	originationDate, paymentAmount, appraisedValue, purchasePrice, universalLoanIdentifier,
			falloutReasons, sellerName, commitmentNumber, clientId, debtToIncome, awardedStatusCount, pricedStatusCount,
			origId, COALESCE(loanAnalystName, loanOfficerUsername), yieldEightYear, loanAnalystName, calculatedRemainingTerm, 
			calculatedSeasoning, originalTerm, acceleratedAmortization, loanType
	FROM bid.loan
	WHERE bidId = @bidId
	AND (@loanStatus = '' OR loanStatus = @loanStatus)
	AND (@searchTextFilter = ''
		 OR 
		 sellerLoanNumber LIKE(@searchTextFilter + '%') 
		 OR 
		 propertyAddress LIKE(@searchTextFilter + '%') 
		 OR 
		 brokerName LIKE(@searchTextFilter + '%') 
		);

	SELECT @sortBy = utilities.sanitizeDynamicSql(@sortBy);
	SELECT @sortDirection = utilities.sanitizeDynamicOrderByDirection(@sortDirection);
	SELECT @loanStatus = COALESCE(@loanStatus, '');

	IF(COALESCE(@sortBy, '') IN('', 'rowNumber'))
	BEGIN;
		SELECT @sortBy = 'loanId';
	END;

	SELECT @statement = 
	 'WITH _sort AS
	  (
		SELECT loanId,
			   ROW_NUMBER() OVER(ORDER BY ' + @sortBy + ' ' + IIF(@sortBy <> 'loanId', @sortDirection, '') + ', loanId DESC) AS rowNumber
		FROM #loans
	  )
	  SELECT loans.loanId,
		     loans.bidId,
		     COALESCE(loans.sellerLoanNumber, '''') AS sellerLoanNumber,
		     COALESCE(loans.borrowerLastName, '''') AS borrowerLastName,
		     COALESCE(loans.currentBalance, 0.00) AS currentBalance, 
		     COALESCE(loans.propertyAddress, '''') AS propertyAddress,
			 COALESCE(loans.recentCredit, 0) AS recentCredit,
		     CAST(ROUND(loans.ltv * 100, 2) AS NUMERIC(12, 2)) AS ltv,
			 CAST(ROUND(loans.price, 2) AS NUMERIC(12, 2)) AS price,
			 CAST(ROUND(loans.totalBid, 1) AS NUMERIC(12, 1)) AS totalBid,
			 NULLIF(accountNumber, 0) AS accountNumber,
			 COALESCE(loans.loanStatus, '''') AS loanStatus,
			 COALESCE(loans.analystComments, '''') AS analystComments,
		     rowNumber,
		     COUNT(*) OVER() AS loanCount,
		     COALESCE(loans.bidName, '''') AS bidName,
			 COALESCE(loans.brokerId, 0) AS brokerId,
			 COALESCE(loans.brokerName, '''') AS brokerName,
			 COALESCE(CAST(ROUND(loans.brokerFeePercentage, 3) AS NUMERIC(12, 3)), 0.00) AS brokerFeePercentage,
			 COALESCE(CAST(ROUND(loans.totalBid, 1) - ROUND(COALESCE(loans.brokerFeePercentage, 0.00), 3) AS NUMERIC(12, 3)), 0.00)  AS sellerBid,
	         COALESCE(loans.propertyState, '''') AS propertyState,
			 COALESCE(loans.borrowerTin, '''') AS borrowerTin,
			 COALESCE(loans.originalBalance, 0.00) AS originalBalance,
			 COALESCE(CAST(ROUND(loans.interestRate, 3) AS NUMERIC(12, 3)), 0.000) AS interestRate,
			 CASE WHEN loans.nextPaymentDue > ''19700101'' THEN loans.nextPaymentDue ELSE NULL END AS nextPaymentDue,
			 COALESCE(loans.loanPurpose, '''') AS loanPurpose,
			 COALESCE(loans.occupancy, '''') AS occupancy,
			 COALESCE(loans.propertyType, '''') AS propertyType,
			 COALESCE(loans.remainingTerm, 0) AS remainingTerm,
			 COALESCE(loans.propertyCity, '''') AS propertyCity,
			 COALESCE(loans.propertyZipCode, '''') AS propertyZipCode,
			 COALESCE(loans.coborrowerLastName, '''') AS coborrowerLastName,
			 COALESCE(loans.coborrowerTin, '''') AS coborrowerTin,
			 CASE WHEN loans.firstPaymentDate > ''19700101'' THEN loans.firstPaymentDAte ELSE NULL END AS firstPaymentDate,
			 loans.lienPosition,
			 CASE WHEN loans.modificationDate > ''19700101'' THEN loans.modificationDate ELSE NULL END AS modificationDate,
			 CASE WHEN loans.originationDate > ''19700101'' THEN loans.originationDate ELSE NULL END  AS originationDate,
			 COALESCE(loans.paymentAmount, 0.00) AS paymentAmount,
			 COALESCE(loans.appraisedValue, 0.00) AS appraisedValue,
			 COALESCE(loans.purchasePrice, 0.00) AS purchasePrice,
			 COALESCE(loans.universalLoanIdentifier, '''') AS universalLoanIdentifier,
			 COALESCE(loans.falloutReasons, '''') AS falloutReasons,
			 COALESCE(loans.sellerName, '''') AS sellerName,
			 COALESCE(loans.commitmentNumber, 0) AS commitmentNumber,
			 COALESCE(loans.clientId, '''') AS clientId,
			 COALESCE(CAST(ROUND(loans.debtToIncome, 2) AS NUMERIC(12, 2)), 0.00) AS debtToIncome,
			 loans.awardedStatusCount,
			 loans.pricedStatusCount,
			 COALESCE(loans.origId, '''') AS origId,
			 COALESCE(loans.loanOfficerUsername, '''') AS loanOfficerUsername,
			 COALESCE(CAST(ROUND(loans.yieldEightYear, 2) AS NUMERIC(12, 2)), 0.00) AS yieldEightYear,
			 COALESCE(loans.loanAnalystName, loans.loanOfficerUsername) AS loanAnalystName,
			 COALESCE(loans.calculatedRemainingTerm, 0) AS calculatedRemainingTerm,
			 COALESCE(loans.calculatedSeasoning, 0) AS calculatedSeasoning,
			 COALESCE(loans.originalTerm, 0) AS originalTerm,
			 COALESCE(loans.acceleratedAmortization, 0) AS acceleratedAmortization, 
			 COALESCE(loans.loanType, '''') AS loanType
	 FROM #loans loans
	 JOIN _sort
		ON _sort.loanId = loans.loanId';

	EXEC utilities.executeSql @statement = @statement,
	                          @pageShowing = @pageShowing;
	
END;
GO